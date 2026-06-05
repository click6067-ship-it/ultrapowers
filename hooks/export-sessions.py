#!/usr/bin/env python3
"""Claude Code 세션 JSONL → 사람이 읽는 markdown 로그 (증분 · 잠금 · prune).

🤖/👤 무엇: ~/.claude/projects/*/*.jsonl 를 $COMMAND_CENTER/logs/ 의 세션별 .md + README 인덱스로 변환.
의도: Stop 훅이 매 세션 종료 시 호출 — 전체 대화를 사람이 읽는 아카이브로 남김.
언제: Stop 훅 자동 실행(또는 수동 `python3 $COMMAND_CENTER/system/export-sessions.py`).

설계(2026-05-27 Codex 카운슬 반영):
- **flock**: 단일 인스턴스. 동시 Stop 훅이 겹쳐도 레이스/부분쓰기 없음. 잠겨있으면 조용히 skip(다음 훅이 따라잡음).
- **증분**: 사이드카 매니페스트(`logs/.export-sessions.json`, 키=원본경로, `mtime_ns`)로 변경/신규 세션만 재파싱. 매 Stop마다 전체 재생성하던 O(전세션) 비용 제거.
- **prune**: 원본 jsonl이 사라진 고아 .md만 삭제 — *이 exporter 네이밍 규칙*(`slug__date__sid.md`) + *매니페스트 추적분*만 대상(README·수기노트 보존).
- 권한: umask 077 → logs/ 0700, .md 0600(raw jsonl과 동일). idempotent.
"""
import json, os, glob, re, fcntl, pathlib

HOME = pathlib.Path.home()
SRC = HOME / ".claude" / "projects"
OUT = pathlib.Path(os.environ.get("COMMAND_CENTER") or (HOME / "main")) / "logs"   # COMMAND_CENTER env honored (기본 $COMMAND_CENTER)
MANIFEST = OUT / ".export-sessions.json"
LOCK = OUT / ".export-sessions.lock"
# HOME 파생 슬러그 prefix — recent-context.py key_to_logslug와 동일 규칙(로그 링크 일치).
HOME_KEY = str(HOME).rstrip("/").replace("/", "-").replace(".", "-")
# prune 안전장치: 이 네이밍에 맞는 파일만 삭제 후보(README.md·수기노트는 절대 제외).
NAME_RE = re.compile(r"^.+__\d{4}-\d{2}-\d{2}__[0-9a-fA-F]{8}\.md$")

os.umask(0o077)
OUT.mkdir(parents=True, exist_ok=True)
try:
    OUT.chmod(0o700)
except OSError:
    pass


def short(d):
    if not isinstance(d, dict): return ""
    for k in ("description", "command", "file_path", "path", "url", "prompt", "pattern", "query"):
        if d.get(k): return str(d[k]).replace("\n", " ")[:80]
    return ""


def blocks_to_md(content):
    out = []
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        for b in content:
            if not isinstance(b, dict): continue
            t = b.get("type")
            if t == "text" and b.get("text", "").strip():
                out.append(b["text"].strip())
            elif t == "tool_use":
                out.append(f"  ↳ `[{b.get('name','tool')}]` {short(b.get('input'))}")
            # thinking / tool_result 는 생략(내부·대용량)
    return "\n\n".join(out)


# 크리덴셜 마스킹(2026-05-31): export 아카이브에 시크릿 값 평문 저장 방지.
# 값 시작이 '·@·( 등 특수문자여도 잡게 관대(과거 redact 누락 교훈). idempotent.
_CRED_RE = re.compile(
    r"""(appkey|appsecret|access_token|approval_key|hashkey|api_key|api_secret|secret_key|secret|token|password|passwd|bearer|authorization|private_key)(["']?\s*[=:]\s*["']?)([^\s"',}\n]{4,})""",
    re.I,
)

# Authorization: Bearer <token> / 단독 Bearer <token> — 토큰 값 전체 마스킹 (key=value 형식 밖이라 별도 처리)
_BEARER_RE = re.compile(r"(?i)\b(bearer\s+)([A-Za-z0-9._~+/\-]{8,}=*)")


def redact_secrets(text):
    """크리덴셜 값을 [REDACTED]로 마스킹 (key=value + Bearer 토큰)."""
    text = _BEARER_RE.sub(lambda m: m.group(1) + "[REDACTED]", text)
    return _CRED_RE.sub(lambda m: m.group(1) + m.group(2) + "[REDACTED]", text)


def atomic_write(path, text):
    """temp 파일에 쓰고 rename — 부분쓰기/동시쓰기 방지(원자적)."""
    tmp = path.with_name(path.name + f".tmp.{os.getpid()}")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def parse_session(jf):
    """전체 파싱 → (turns[md], first_ts, last_ts). 변경/신규 세션에만 호출(비용 한정)."""
    turns, first_ts, last_ts = [], None, None
    for line in jf.open(encoding="utf-8", errors="ignore"):
        try:
            o = json.loads(line)
        except Exception:
            continue
        typ = o.get("type")
        if typ not in ("user", "assistant"): continue
        ts = o.get("timestamp", "")
        if ts:
            first_ts = first_ts or ts
            last_ts = ts
        md = blocks_to_md(o.get("message", {}).get("content"))
        # tool_result 만 든 user 턴(도구 출력 되먹임)은 md가 "" → 드롭.
        if not md or md.strip() in ("", "(no content)"): continue
        who = "🧑 User" if typ == "user" else "🤖 Claude"
        hhmm = ts[11:16] if len(ts) >= 16 else ""
        turns.append(f"### {who}  ·  {hhmm}\n\n{md}\n")
    return turns, first_ts, last_ts


def main():
    # 단일 인스턴스(비차단). 다른 export가 도는 중이면 skip — 다음 Stop 훅이 따라잡음.
    lockf = open(LOCK, "w")
    try:
        fcntl.flock(lockf, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return 0

    manifest = {}
    if MANIFEST.exists():
        try:
            manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        except Exception:
            manifest = {}

    new_manifest, reparsed = {}, 0
    for proj in sorted(SRC.glob("*")):
        if not proj.is_dir(): continue
        slug = proj.name.replace(HOME_KEY + "-", "").strip("-") or "root"
        for jf in sorted(proj.glob("*.jsonl")):
            key = str(jf)
            try:
                mtime_ns = jf.stat().st_mtime_ns
            except OSError:
                continue
            prev = manifest.get(key)
            # 변경 없음 + 항목 온전 + 산출물 존재 → 재파싱 없이 재사용(증분 핵심).
            # 손상/구버전 매니페스트 항목(필드 누락)은 재사용 않고 재파싱 → 인덱스 빌드 크래시 방지.
            if (prev and prev.get("mtime_ns") == mtime_ns
                    and all(k in prev for k in ("name", "date", "slug", "turns"))
                    and (OUT / prev["name"]).exists()):
                new_manifest[key] = prev
                continue
            turns, first_ts, last_ts = parse_session(jf)
            if not turns:
                continue
            date = (first_ts or "")[:10] or "unknown"
            sid = jf.stem[:8]
            name = f"{slug}__{date}__{sid}.md"
            header = (f"# {slug} · {date}\n\n세션 `{jf.stem}` · {len(turns)} turns · "
                      f"{(first_ts or '')[:19]} → {(last_ts or '')[:19]}\n\n---\n\n")
            atomic_write(OUT / name, redact_secrets(header + "\n".join(turns)))
            new_manifest[key] = {"mtime_ns": mtime_ns, "name": name,
                                 "date": date, "slug": slug, "turns": len(turns)}
            reparsed += 1

    # prune: 매니페스트에 *있었으나* 이제 소스가 사라진 항목의 .md만 삭제(네이밍 규칙 매칭 한정).
    live_names = {e["name"] for e in new_manifest.values()}
    for key, e in manifest.items():
        if key in new_manifest:
            continue
        nm = e.get("name", "")
        f = OUT / nm
        if nm and NAME_RE.match(nm) and nm not in live_names and f.exists():
            try:
                f.unlink()
            except OSError:
                pass

    # README 인덱스 = 매니페스트 전체로 재구성(스킵된 세션도 포함 — 드리프트 없음).
    index = sorted(((e["date"], e["slug"], e["turns"], e["name"]) for e in new_manifest.values()),
                   reverse=True)
    idx_md = ("# 📜 세션 로그 (최신순)\n\n자동 생성(증분) — `python3 $COMMAND_CENTER/system/export-sessions.py` "
              "재실행으로 갱신.\n\n| 날짜 | 프로젝트 | turns | 파일 |\n|---|---|---|---|\n")
    for date, slug, n, name in index:
        idx_md += f"| {date} | {slug} | {n} | [{name}](./{name}) |\n"
    atomic_write(OUT / "README.md", idx_md)
    MANIFEST.write_text(json.dumps(new_manifest, ensure_ascii=False), encoding="utf-8")

    print(f"✅ {len(new_manifest)} 세션 (이번 재파싱 {reparsed}) → {OUT}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as e:
        import sys
        sys.stderr.write(f"[export-sessions] error: {e}\n")
        raise SystemExit(0)
