#!/usr/bin/env python3
"""SessionEnd hook — 프로젝트 repo마다 정제된 개발 일지(DEVLOG.md)를 자동 축적.

🤖 무엇: 세션이 끝날 때 그 세션의 대화 전체를 LLM(haiku)으로 정제·요약해
   <repo루트>/DEVLOG.md 에 "요청 의도 / 실제 작업 / 결정·이유 / 미완" 형식으로 쌓는다.
   worklog(~/main/worklog, 메타 요약)와 별개 — 이건 *그 프로젝트 폴더 안에* 남는,
   타인이 읽어도 맥락이 잡히는 기록 (니즈 2026-07-16: "정제+요약된 대화내역+시간+실제 작업").

설계:
- **게이트**: cwd가 DEVLOG_SCOPE(기본 ~/ghq) 아래의 git repo일 때만. 사용자 발화 <2 스킵.
- **detach**: SessionEnd는 종료를 블록하므로 훅 본체는 이벤트만 받고 즉시 워커를
  분리 실행(start_new_session) 후 exit 0. LLM 호출(수십 초)은 워커에서.
- **재귀 가드**: 워커의 `claude -p` 자식에 CLAUDE_DEVLOG_ACTIVE=1 → 그 세션의 훅은 즉시 exit.
- **폴백**: LLM 실패/타임아웃 시 결정론 요약(첫·마지막 프롬프트+통계)으로라도 기록.
- **시크릿**: digest·산출물 모두 redact (DEVLOG.md는 원격 git에 실릴 수 있다).
- **idempotent**: 항목마다 `devlog:entry <sid>` 마커 — 같은 세션 재발동 시 그 블록만 교체.
- **원자성**: temp+rename (WSL VM 회수 중 truncate 방어), repo별 flock.
- 실패해도 세션 안 막음(exit 0) + hooks.log 기록(무음 금지).

env: DEVLOG_SCOPE(콜론 구분 경로 prefix들, 기본 ~/ghq) · DEVLOG_MODEL(기본 haiku)
     · DEVLOG_TIMEOUT(초, 기본 300) · DEVLOG_DISABLE=1(끄기)
수동 실행: python3 devlog.py --worker <event.json>  (event = SessionEnd 훅 stdin 형식)
"""
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from redaction import redact

HOME = Path.home()
HOOKS_LOG = Path(os.environ.get("COMMAND_CENTER") or (HOME / "main")) / "logs" / "hooks.log"
DEFAULT_SCOPE = str(HOME / "ghq")
MODEL = os.environ.get("DEVLOG_MODEL", "claude-haiku-4-5-20251001")
TIMEOUT = int(os.environ.get("DEVLOG_TIMEOUT", "300"))
ENTRIES_MARK = "<!-- devlog:entries -->"

# ── 시크릿 마스킹 (export-sessions.py와 동일 규칙 — DEVLOG는 커밋될 수 있어 필수) ──
_CRED_RE = re.compile(
    r"""(KIS_APP_KEY|KIS_APP_SECRET|KIS_CANO|KIS_ACCOUNT|KRX_ID|KRX_PW|DART_API_KEY|appkey|appsecret|access_token|approval_key|hashkey|api_key|api_secret|secret_key|secret|token|password|passwd|bearer|authorization|private_key)(["']?\s*[=:]\s*["']?)([^\s"',}\n]{4,})""",
    re.I,
)
_BEARER_RE = re.compile(r"(?i)\b(bearer\s+)([A-Za-z0-9._~+/\-]{8,}=*)")


def log(msg: str):
    try:
        HOOKS_LOG.parent.mkdir(parents=True, exist_ok=True)
        with HOOKS_LOG.open("a") as f:
            f.write(f"{datetime.now().isoformat(timespec='seconds')} [devlog] {msg}\n")
    except Exception:
        pass


# ── transcript 파싱 ──────────────────────────────────────────────
_HARNESS_NOISE = ("<local-command-caveat>", "<command-name>", "<local-command-stdout>",
                  "<task-notification>", "<system-reminder>", "Caveat: The messages below")


def is_noise(txt: str) -> bool:
    head = txt.lstrip()[:60]
    return any(head.startswith(m) for m in _HARNESS_NOISE)


def parse_transcript(path: str):
    """turns=[('user'|'claude', hhmm, text)], files=set(편집 파일), stats."""
    turns, files = [], []
    tools = 0
    first_ts = last_ts = None
    user_msgs = 0
    if not path or not os.path.isfile(path):
        return turns, files, tools, user_msgs, first_ts, last_ts
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                o = json.loads(line)
            except Exception:
                continue
            typ = o.get("type")
            if typ not in ("user", "assistant"):
                continue
            ts = o.get("timestamp", "")
            if ts:
                first_ts = first_ts or ts
                last_ts = ts
            hhmm = ts[11:16] if len(ts) >= 16 else ""
            content = o.get("message", {}).get("content")
            if typ == "user":
                if isinstance(content, list):
                    if any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
                        continue
                    txt = " ".join(b.get("text", "") for b in content
                                   if isinstance(b, dict) and b.get("type") == "text").strip()
                else:
                    txt = str(content or "").strip()
                if txt and not is_noise(txt):
                    turns.append(("user", hhmm, txt))
                    user_msgs += 1
            else:
                texts = []
                if isinstance(content, list):
                    for b in content:
                        if not isinstance(b, dict):
                            continue
                        if b.get("type") == "text" and b.get("text", "").strip():
                            texts.append(b["text"].strip())
                        elif b.get("type") == "tool_use":
                            tools += 1
                            inp = b.get("input") or {}
                            if b.get("name") in ("Edit", "Write", "NotebookEdit") and inp.get("file_path"):
                                files.append(str(inp["file_path"]))
                if texts:
                    turns.append(("claude", hhmm, texts[-1]))  # 턴의 결론 텍스트만
    # 편집 파일: 순서 보존 dedupe
    seen, uniq = set(), []
    for p in files:
        if p not in seen:
            seen.add(p)
            uniq.append(p)
    return turns, uniq, tools, user_msgs, first_ts, last_ts


def local_dt(iso: str):
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone()
    except Exception:
        return None


def dur_str(a, b):
    da, db = local_dt(a or ""), local_dt(b or "")
    if not da or not db:
        return "?"
    m = int((db - da).total_seconds() // 60)
    return f"{m // 60}h{m % 60:02d}m" if m >= 60 else f"{m}m"


def trunc(s: str, n: int) -> str:
    s = s.replace("\r", " ").strip()
    return s if len(s) <= n else s[:n].rstrip() + " …"


# ── digest (LLM 입력) ────────────────────────────────────────────
def build_digest(turns, files, repo_name, branch, first_ts, last_ts, tools, cap=40000):
    lines = [f"[프로젝트] {repo_name} · 브랜치 {branch} · 소요 {dur_str(first_ts, last_ts)} · 도구호출 {tools}"]
    if files:
        lines.append("[편집 파일] " + ", ".join(files[:30]) + (f" 외 {len(files)-30}개" if len(files) > 30 else ""))
    lines.append("[대화]")
    for who, hhmm, txt in turns:
        tag = "USER" if who == "user" else "CLAUDE"
        limit = 600 if who == "user" else 350
        lines.append(f"({hhmm}) {tag}: {trunc(txt, limit)}")
    digest = "\n".join(lines)
    if len(digest) > cap:  # 초과 시 중간 생략 (앞뒤 보존 — 시작 의도·마지막 결론이 중요)
        digest = digest[: cap // 2] + "\n…(중략)…\n" + digest[-cap // 2:]
    return redact(digest)


PROMPT = """당신은 개발 일지 작성자다. 아래는 한 Claude Code 세션의 대화 digest다.
이걸 제3자(팀원)가 읽어도 바로 맥락을 잡을 수 있는 한국어 개발 일지 항목으로 정제하라.

규칙:
- 사용자의 말을 그대로 옮기지 말고 의도를 정제해서 써라. digest에 없는 내용을 지어내지 마라.
- 크리덴셜·토큰·비밀번호는 절대 포함 금지.
- 전체 1500자 이내. 불릿은 간결한 완결문으로.
- 정확히 아래 형식으로만 출력(다른 말·코드펜스 금지):

제목: <이 세션을 한 줄로 — 예: "결제 실패 버그 수정 및 회귀 테스트 추가">
**요청:** <사용자가 무엇을 왜 원했는지 정제 (1-2문장)>
**작업:**
- <실제 수행한 작업들 — 시간 순, 구체적으로 (3-7개 불릿)>
**결정·이유:** <내린 기술적/방향 결정과 근거 (없으면 "없음")>
**미완·다음:** <끝내지 못한 것, 이어서 할 일 (없으면 "없음")>

=== DIGEST ===
"""


def find_claude() -> str:
    p = shutil.which("claude")
    if p:
        return p
    for c in sorted(glob.glob(str(HOME / ".nvm/versions/node/*/bin/claude")), reverse=True):
        return c
    return "claude"


def llm_refine(digest: str):
    """claude -p (haiku) 호출 → (title, body) 또는 None."""
    env = dict(os.environ, CLAUDE_DEVLOG_ACTIVE="1")
    try:
        r = subprocess.run(
            [find_claude(), "-p", PROMPT + digest, "--model", MODEL,
             "--output-format", "text", "--strict-mcp-config"],
            capture_output=True, text=True, timeout=TIMEOUT, env=env,
            cwd=str(HOME),  # 프로젝트 폴더 밖에서 실행 — 프로젝트 훅/컨텍스트 오염 방지
        )
    except subprocess.TimeoutExpired:
        log(f"llm timeout({TIMEOUT}s) — fallback")
        return None
    except Exception as e:
        log(f"llm error: {e} — fallback")
        return None
    if r.returncode != 0 or not r.stdout.strip():
        log(f"llm rc={r.returncode} stderr={trunc(r.stderr or '', 200)} — fallback")
        return None
    out = r.stdout.strip()
    title = ""
    body_lines = []
    for ln in out.splitlines():
        if not title and ln.strip().startswith("제목:"):
            title = ln.split(":", 1)[1].strip()
            continue
        body_lines.append(ln)
    body = "\n".join(body_lines).strip()
    if not body:
        return None
    return (title or "세션 기록", trunc(body, 4000))


def fallback_body(turns, user_msgs, tools):
    first = next((t for w, _, t in turns if w == "user" for t in [t]), "")
    last = next((t for w, _, t in reversed(turns) if w == "user" for t in [t]), "")
    return ("**요청:** " + trunc(first, 300) + "\n"
            + (f"**마지막 지시:** {trunc(last, 300)}\n" if last != first else "")
            + f"**작업:** (자동요약 실패 — 원본 로그 참조) 사용자 발화 {user_msgs} · 도구호출 {tools}\n"
            + "**미완·다음:** 로그 확인 필요")


# ── DEVLOG.md 쓰기 ───────────────────────────────────────────────
def devlog_header(repo_name: str) -> str:
    return f"""# DEVLOG — {repo_name}

> Claude Code 세션이 끝날 때마다 자동으로 쌓이는 **개발 일지**입니다 (SessionEnd 훅 `~/main/system/devlog.py`).
> 항목 1개 = 세션 1개: **요청 의도(정제) · 실제 수행 작업 · 결정과 이유 · 미완 항목 · 터치한 파일.**
> 최신이 위. 수동 편집 가능하나 `devlog:entry` 주석 마커는 지우지 마세요(세션 중복 방지 키).

{ENTRIES_MARK}
"""


def upsert_entry(devlog: Path, sid: str, entry_md: str, repo_name: str):
    """flock + 마커 기반 upsert + 원자적 쓰기."""
    import fcntl
    lock_path = Path(tempfile.gettempdir()) / f"devlog-{abs(hash(str(devlog)))}.lock"
    with open(lock_path, "w") as lockf:
        fcntl.flock(lockf, fcntl.LOCK_EX)
        text = devlog.read_text(encoding="utf-8") if devlog.exists() else devlog_header(repo_name)
        if ENTRIES_MARK not in text:  # 수동 편집으로 마커 유실 → 최상단 복구
            text = ENTRIES_MARK + "\n" + text
        begin = f"<!-- devlog:entry {sid} -->"
        end = f"<!-- /devlog:entry {sid} -->"
        block = f"{begin}\n{entry_md}\n{end}"
        if begin in text and end in text:  # 같은 세션 재발동 → 교체
            pre, rest = text.split(begin, 1)
            _, post = rest.split(end, 1)
            text = pre + block + post
        else:  # 새 항목 → 마커 바로 아래(최신이 위)
            text = text.replace(ENTRIES_MARK, ENTRIES_MARK + "\n\n" + block, 1)
        tmp = devlog.with_name(devlog.name + f".tmp.{os.getpid()}")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, devlog)


# ── 워커 (detached) ──────────────────────────────────────────────
def worker(event_path: str) -> int:
    e = json.loads(Path(event_path).read_text(encoding="utf-8"))
    try:
        os.unlink(event_path)
    except OSError:
        pass
    cwd = e.get("cwd", "")
    sid = (e.get("session_id") or "nosid")[:8]
    turns, files, tools, user_msgs, first_ts, last_ts = parse_transcript(e.get("transcript_path", ""))
    if user_msgs < 2:
        return 0
    # repo 루트
    try:
        root = subprocess.run(["git", "-C", cwd, "rev-parse", "--show-toplevel"],
                              capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:
        root = ""
    if not root:
        return 0
    repo = Path(root)
    branch = ""
    try:
        branch = subprocess.run(["git", "-C", root, "rev-parse", "--abbrev-ref", "HEAD"],
                                capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:
        pass

    digest = build_digest(turns, files, repo.name, branch or "?", first_ts, last_ts, tools)
    refined = llm_refine(digest)
    if refined:
        title, body = refined
    else:
        title, body = "세션 기록 (자동요약 실패 — 폴백)", fallback_body(turns, user_msgs, tools)

    dt = local_dt(first_ts or "") or datetime.now().astimezone()
    stamp = dt.strftime("%Y-%m-%d %H:%M")
    rels = []
    for p in files:
        try:
            rels.append(str(Path(p).resolve().relative_to(repo.resolve())))
        except ValueError:
            rels.append(p)
    files_line = ("\n**터치한 파일:** " + " · ".join(f"`{p}`" for p in rels[:15])
                  + (f" 외 {len(rels)-15}개" if len(rels) > 15 else "")) if rels else ""
    entry = (f"## {stamp} — {redact(title)}\n"
             f"<sub>세션 `{sid}` · {dur_str(first_ts, last_ts)} · 발화 {user_msgs} · 도구 {tools}"
             + (f" · 브랜치 `{branch}`" if branch else "") + "</sub>\n\n"
             + redact(body) + files_line + "\n")
    upsert_entry(repo / "DEVLOG.md", sid, entry, repo.name)
    log(f"OK {repo.name} sid={sid} ({'llm' if refined else 'fallback'})")
    return 0


# ── 훅 본체 (즉시 리턴) ──────────────────────────────────────────
def hook_main() -> int:
    if os.environ.get("DEVLOG_DISABLE") == "1" or os.environ.get("CLAUDE_DEVLOG_ACTIVE") == "1":
        return 0
    try:
        e = json.load(sys.stdin)
    except Exception:
        return 0
    cwd = e.get("cwd") or ""
    scopes = [s for s in (os.environ.get("DEVLOG_SCOPE") or DEFAULT_SCOPE).split(":") if s]
    if not any(os.path.abspath(cwd).startswith(os.path.abspath(os.path.expanduser(s)) + os.sep)
               or os.path.abspath(cwd) == os.path.abspath(os.path.expanduser(s)) for s in scopes):
        return 0
    fd, tmp = tempfile.mkstemp(prefix="devlog-event-", suffix=".json")
    with os.fdopen(fd, "w") as f:
        json.dump(e, f)
    logf = open(HOOKS_LOG, "a") if HOOKS_LOG.parent.exists() else subprocess.DEVNULL
    subprocess.Popen([sys.executable, os.path.abspath(__file__), "--worker", tmp],
                     stdout=logf, stderr=logf, start_new_session=True)
    return 0


if __name__ == "__main__":
    try:
        if len(sys.argv) >= 3 and sys.argv[1] == "--worker":
            sys.exit(worker(sys.argv[2]))
        sys.exit(hook_main())
    except Exception as ex:
        log(f"ERROR {ex}")
        sys.exit(0)
