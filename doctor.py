#!/usr/bin/env python3
"""doctor.py — Claude/Codex/Orca 에이전트 시스템 헬스체크.

거의 읽기 전용 진단(예외: `.doctor-state.json` 스냅샷만 best-effort 갱신 — 쓰기 실패해도 진단 계속).
손대지 않고 '지금 무엇이 어긋났나'만 보고한다.
점검: Codex 실효 정책 · Orca WSL launcher · 메모리/dotclaude 미러 drift ·
hooks 무결성·canary · 활성 plugins · 누적물 · 런타임 버전.
이식 가능: COMMAND_CENTER env(기본 ~/main)로 미러 위치 결정.

사용: python3 ~/main/system/doctor.py   (또는 deploy/install 끝에 자동 실행)
"""
import json
import os
import re
import selectors
import subprocess
import time
import datetime as dt
from pathlib import Path

HOME = Path.home()
CC = Path(os.environ.get("COMMAND_CENTER", str(HOME / "main")))  # 이식: 미러·로그 홈
OK, WARN, INFO = "✓", "! ", "·"
issues = 0


def age(mtime: float) -> str:
    if not mtime:
        return "없음"
    d = (time.time() - mtime) / 86400
    return "오늘" if d < 1 else f"{int(d)}일전"


def mem_stat(p: Path):
    files = list(p.rglob("*.md")) if p.exists() else []
    latest = max((f.stat().st_mtime for f in files), default=0)
    return len(files), latest


def section(t):
    print(f"\n[{t}]")


def ver(name, args):
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=10)
        blob = (r.stdout + r.stderr).strip()
        return blob.splitlines()[0] if blob else "?"
    except Exception:
        return None


def codex_hooks_list(cwd: Path, codex_home: Path, timeout: float = 8.0):
    """Query the installed Codex app-server without closing stdin prematurely."""
    env = os.environ.copy()
    env["CODEX_HOME"] = str(codex_home)
    proc = subprocess.Popen(
        ["codex", "app-server", "--stdio"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        env=env,
    )
    selector = selectors.DefaultSelector()
    assert proc.stdin is not None and proc.stdout is not None
    selector.register(proc.stdout, selectors.EVENT_READ)

    def send(payload):
        proc.stdin.write(json.dumps(payload, separators=(",", ":")) + "\n")
        proc.stdin.flush()

    def receive(response_id, deadline):
        while time.monotonic() < deadline:
            ready = selector.select(max(0.0, deadline - time.monotonic()))
            if not ready:
                break
            line = proc.stdout.readline()
            if not line:
                break
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            if message.get("id") == response_id:
                return message
        raise TimeoutError(f"Codex app-server response {response_id} timed out")

    try:
        deadline = time.monotonic() + timeout
        send(
            {
                "method": "initialize",
                "id": 0,
                "params": {
                    "clientInfo": {
                        "name": "agent_system_doctor",
                        "title": "Agent System Doctor",
                        "version": "1.0",
                    }
                },
            }
        )
        init = receive(0, deadline)
        if "error" in init:
            raise RuntimeError(init["error"].get("message", "initialize failed"))
        send({"method": "initialized", "params": {}})
        send({"method": "hooks/list", "id": 1, "params": {"cwds": [str(cwd)]}})
        response = receive(1, deadline)
        if "error" in response:
            raise RuntimeError(response["error"].get("message", "hooks/list failed"))
        return response["result"]["data"][0]
    finally:
        selector.close()
        if proc.stdin:
            proc.stdin.close()
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=2)


print("\nAgent system doctor\n" + "-" * 50)

# 1. Codex auth (kickoff 무성실패 방지)
section("codex auth")
v = ver("codex", ["codex", "login", "status"])
if v and "logged in" in v.lower():
    print(f" {OK} {v}")
else:
    print(f" {WARN} 로그인 확인 필요: {v or 'codex 없음'}")
    issues += 1

# 1b. Orca가 리다이렉트한 CODEX_HOME의 실효 정책
section("codex effective policy")
runtime_home = HOME / ".local/share/orca/codex-runtime-home/home"
canonical_home = HOME / ".codex"
syncer = CC / "system/sync-orca-codex-home.py"
if syncer.exists() and runtime_home.exists():
    try:
        r = subprocess.run(
            [os.environ.get("PYTHON", "python3"), str(syncer), "--check", "--quiet"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if r.returncode == 0:
            print(f" {OK} 정본 AGENTS + runtime guardrail/trust + WSL launcher 동기")
        else:
            print(f" {WARN} Orca CODEX_HOME policy drift — sync-orca-codex-home.py 실행 필요")
            issues += 1
    except Exception as e:
        print(f" {WARN} Orca CODEX_HOME policy 점검 실패: {e}")
        issues += 1
else:
    print(f" {INFO} Orca CODEX_HOME 또는 sync 도구 없음")

wrapper = HOME / ".local/bin/codex"
if wrapper.exists() and "sync-orca-codex-home.py" in wrapper.read_text(errors="ignore"):
    print(f" {OK} Codex 시작 전 policy sync wrapper 활성")
else:
    print(f" {WARN} Codex policy sync wrapper 미설정")
    issues += 1

for label, config in (
    ("canonical", canonical_home / "config.toml"),
    ("orca-runtime", runtime_home / "config.toml"),
):
    if not config.exists():
        continue
    text = config.read_text(errors="ignore")
    inline = bool(re.search(r"^FIRECRAWL_API_KEY\s*=", text, re.M))
    forwarded = 'env_vars = ["FIRECRAWL_API_KEY"]' in text
    if inline:
        print(f" {WARN} {label}: Firecrawl 키 평문 설정 존재")
        issues += 1
    elif forwarded:
        print(f" {OK} {label}: Firecrawl env forwarding (평문 없음)")
    else:
        print(f" {WARN} {label}: Firecrawl credential 전달 설정 불명")
        issues += 1

if runtime_home.exists():
    try:
        hook_data = codex_hooks_list(CC, runtime_home)
        active = [hook for hook in hook_data.get("hooks", []) if hook.get("enabled")]
        untrusted = [
            hook
            for hook in active
            if hook.get("trustStatus") not in {"trusted", "managed"}
        ]
        errors = hook_data.get("errors", [])
        if untrusted or errors:
            labels = ", ".join(
                f"{hook.get('eventName')}:{hook.get('trustStatus')}"
                for hook in untrusted
            )
            print(
                f" {WARN} Orca runtime 활성 hook 신뢰 실패"
                f"{f': {labels}' if labels else ''}"
            )
            issues += max(1, len(untrusted) + len(errors))
        else:
            print(f" {OK} Orca runtime 활성 hook {len(active)}개 전부 trusted")
    except Exception as e:
        print(f" {WARN} Orca runtime hook 신뢰 점검 실패: {e}")
        issues += 1

orca_ide = HOME / ".local/bin/orca-ide"
if orca_ide.exists():
    try:
        bridge_probe = subprocess.run(
            [
                str(orca_ide),
                "terminal",
                "wait",
                "--terminal",
                "__doctor_missing__",
                "--for",
                "tui-idle",
                "--timeout-ms",
                "1",
                "--json",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        payload = json.loads(bridge_probe.stdout)
        error_code = (payload.get("error") or {}).get("code")
        if payload.get("ok") is False and error_code == "terminal_handle_stale":
            print(f" {OK} Orca WSL bridge named-flag 전달 정상")
        else:
            print(f" {WARN} Orca WSL bridge canary 예상외 응답")
            issues += 1
    except Exception as e:
        print(f" {WARN} Orca WSL bridge named-flag 전달 실패: {e}")
        issues += 1

# 2. 메모리 미러 drift (수동 sync 누락 탐지)
section("memory mirror drift")
canon = HOME / ".claude/projects"
mirror = CC / "system/memory-snapshot"
drift = 0
if not mirror.exists():
    print(f" {INFO} 미러 없음: {mirror} — drift 점검 skip (memory-snapshot 미러 미사용 설치에선 정상)")
elif canon.exists():
    for proj in sorted(canon.glob("*/memory")):
        key = proj.parent.name
        cn, cm = mem_stat(proj)
        if cn == 0:
            continue
        mn, mm = mem_stat(mirror / key)
        if cn != mn or cm > mm + 2:
            print(f" {WARN} {key}: 정본 {cn}개/{age(cm)} != 미러 {mn}개/{age(mm)}")
            drift += 1
if drift:
    print(f" {WARN} {drift}개 프로젝트 미러 drift -> sync 필요")
    issues += drift
elif mirror.exists():
    print(f" {OK} 메모리 미러 동기")

# 2b. dotclaude 자산 미러 drift (skills/rules/agents/workflows/CLAUDE.md — 새 자산이 이식 미러에서 조용히 빠지는 사각 제거, 2026-07-06)
section("dotclaude mirror drift")
dc = CC / "system/dotclaude"
_SKIP = {"node_modules", "__pycache__", ".git", "chromedeps"}  # sync.sh 기본 미동기 대상과 정합


def asset_stat(root: Path):
    if not root.exists():
        return set(), 0
    files = [f for f in root.rglob("*") if f.is_file() and not (_SKIP & {p.name for p in f.parents})]
    return {str(f.relative_to(root)) for f in files}, max((f.stat().st_mtime for f in files), default=0)


if dc.exists():
    dc_drift = 0
    for cat in ("skills", "rules", "agents", "workflows"):
        lnames, lm = asset_stat(HOME / ".claude" / cat)
        mnames, mm = asset_stat(dc / cat)
        missing = sorted(lnames - mnames)  # 미러 여분은 sync.sh prune 몫 — 여기선 누락·낡음만
        if missing or lm > mm + 2:
            what = f"미러 누락 {len(missing)}개: {', '.join(missing[:3])}{'…' if len(missing) > 3 else ''}" if missing else "라이브가 미러보다 최신"
            print(f" {WARN} {cat}: {what} -> bash {dc}/sync.sh --manual")
            dc_drift += 1
    gc, mc = HOME / ".claude/CLAUDE.md", dc / "CLAUDE.md"
    if gc.exists() and (not mc.exists() or gc.stat().st_mtime > mc.stat().st_mtime + 2):
        print(f" {WARN} CLAUDE.md: 라이브가 미러보다 최신 -> bash {dc}/sync.sh --manual")
        dc_drift += 1
    issues += dc_drift
    if not dc_drift:
        print(f" {OK} dotclaude 미러 동기 (skills/rules/agents/workflows/CLAUDE.md)")
else:
    print(f" {INFO} dotclaude 미러 없음 (이식 미러 미사용이면 무시)")

# 3. hooks 무결성 (설정된 훅 스크립트가 실제 존재하나)
section("hooks")
settings = HOME / ".claude/settings.json"
cfg = {}
try:
    cfg = json.loads(settings.read_text())
    for event, groups in cfg.get("hooks", {}).items():
        for g in groups:
            for h in g.get("hooks", []):
                cmd = h.get("command", "")
                # wrapper 형태(`if [ -f /path ] ...; then /bin/sh /path; fi`)에서 첫 토큰은 `if`다.
                # 그걸 훅 이름으로 삼으면 실제 스크립트가 없어도 ✓가 찍힌다 — Orca bridge가 죽어도
                # doctor는 건강하다고 보고했다 (2026-07-29 2백본 감사). 명령 문자열의 절대경로를
                # 전부 뽑아 각각 존재를 검사한다.
                paths = list(dict.fromkeys(
                    p for p in re.findall(r"/[^\s\"';|)]+", cmd)
                    if re.search(r"\.(py|sh|mjs|js)$", p)))
                if not paths:
                    print(f" {OK} {event}: (스크립트 경로 없음) {cmd[:36]}")
                    continue
                missing = [p for p in paths if not Path(p).exists()]
                for p in missing:
                    print(f" {WARN} {event}: 스크립트 없음 -> {p}")
                issues += len(missing)
                if not missing:
                    print(f" {OK} {event}: {', '.join(Path(p).name for p in paths)}")
except Exception as e:
    print(f" {WARN} settings.json 파싱 실패: {e}")
    issues += 1

# 3c. 훅 진입점 실제 canary (파일 존재만으로 PASS하는 false-green 차단)
section("hook canaries")
canary_suites = [
    ("guardrail", [os.environ.get("PYTHON", "python3"), str(CC / "system/guardrail_test.py")]),
    ("session-end", [os.environ.get("PYTHON", "python3"), str(CC / "system/session_end_runner_test.py")]),
    ("skill-usage", [os.environ.get("PYTHON", "python3"), str(CC / "system/skill_usage_log_test.py")]),
    ("remaining-hooks", [os.environ.get("PYTHON", "python3"), str(CC / "system/hook_smoke_test.py"), "--quiet"]),
]
for label, command in canary_suites:
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=30)
    except Exception as e:
        print(f" {WARN} {label}: canary 실행 실패: {e}")
        issues += 1
        continue
    if result.returncode == 0:
        print(f" {OK} {label}")
    else:
        detail = (result.stderr or result.stdout).strip().splitlines()
        print(f" {WARN} {label}: {detail[-1][:100] if detail else '실패'}")
        issues += 1

# 3b. rules entrypoint 무결성 (CLAUDE.md가 참조하는 rules 파일이 실재하나 — 공개판 rules 누락류 차단, 2026-07-03 Codex B3)
section("rules entrypoint")
gclaude = HOME / ".claude/CLAUDE.md"
rules_dir = HOME / ".claude/rules"
if gclaude.exists():
    import re as _re
    # 2026-07-31 확장(다이어트 redteam 발견2): CLAUDE.md만이 아니라 rules끼리의
    # 상호참조(예: design-antislop → phase0-gate)도 스캔 — 파일 통합·개명 시 false-green 방지
    _scan_srcs = [gclaude] + (sorted(rules_dir.glob("*.md")) if rules_dir.exists() else [])
    refd = {}
    for _src in _scan_srcs:
        for _name in _re.findall(r'rules/([a-z0-9-]+)\.md', _src.read_text()):
            refd.setdefault(_name, _src.name)
    present = {p.stem for p in rules_dir.glob("*.md")} if rules_dir.exists() else set()
    missing = {n: src for n, src in refd.items() if n not in present}
    if missing:
        for _n, _src in sorted(missing.items()):
            print(f" {WARN} {_src}가 참조하는 rules 부재: rules/{_n}.md")
        issues += 1
    else:
        print(f" {OK} rules {len(present)}개, 참조 {len(refd)}개(CLAUDE.md+rules 상호) 전부 실재")

# 3c. skill 참조 무결성 (2026-07-30 전면감사 A② — superpowers류 재발 차단:
# 스킬·rules 본문이 가리키는 스킬/플러그인이 실제 로드 가능한가. 1d는 인스턴스 수리, 이건 클래스 수리)
section("skill 참조 무결성")
skills_dir = HOME / ".claude/skills"
wf_dir = HOME / ".claude/workflows"
loadable = {p.name for p in skills_dir.iterdir() if p.is_dir()} if skills_dir.exists() else set()
if wf_dir.exists():
    loadable |= {p.stem for p in wf_dir.glob("*.md")}
_BUILTIN_SLASH = {
    "plugin", "mcp", "model", "config", "hooks", "clear", "help", "effort", "fast",
    "code-review", "ultrareview", "init", "review", "security-review", "compact", "sandbox",
    "workflows", "loop", "schedule", "install-slack-app", "simplify", "run", "dataviz",
    "update-config", "statusline", "resume", "rewind", "export", "context", "cost", "doctor",
    # 경로·일반어 오탐 가드
    "home", "tmp", "dev", "usr", "etc", "bin", "mnt", "opt", "var", "proc",
}
_disabled_plugins = {name.split("@")[0] for name, on in (cfg.get("enabledPlugins", {}) or {}).items() if on is False}
_scan = list(skills_dir.glob("*/SKILL.md")) + list(skills_dir.glob("*/references/*.md")) + \
        (list(rules_dir.glob("*.md")) if rules_dir.exists() else [])
_ref_issues = []
import re as _re2
for _f in _scan:
    try:
        _body = _f.read_text()
    except Exception:
        continue
    _rel = str(_f).replace(str(HOME), "~")
    # 사실 서술 문맥("비활성이라", "deferred", "슬래시커맨드가 아니라")은 실행 참조가 아니다
    _EXEMPT_CTX = r"비활성|이식|disabled|deferred|없|않|리터럴|제거|사고|폐기|과거|였|아니라|예정"
    # 'codex'는 CLI 바이너리 이름과 겹쳐 단어 스캔이 오탐 — 플러그인 호출형(/codex:...)만 검사
    _AMBIGUOUS_PLUGIN_NAMES = {"codex"}
    for _plug in _disabled_plugins:
        _pat = rf"/{_re2.escape(_plug)}:[a-z]" if _plug in _AMBIGUOUS_PLUGIN_NAMES else rf"\b{_re2.escape(_plug)}\b"
        for _m in _re2.finditer(_pat, _body):
            _line = _body.count("\n", 0, _m.start()) + 1
            _ctx = _body[max(0, _m.start() - 80):_m.start() + 80].replace("\n", " ")
            if _re2.search(_EXEMPT_CTX, _ctx):
                continue
            _ref_issues.append(f"{_rel}:{_line}: 비활성 플러그인 '{_plug}' 실행 참조")
            break
    # 슬래시 스킬 참조 스캔은 이 시스템이 저작한 파일만 (한국어 본문 = 자작 스킬·rules 휴리스틱 —
    # 영어 서드파티 스킬팩의 CSS·페이지경로·"A/B" 산문이 오탐의 전부였다, 2026-07-30 실측)
    _ours = bool(_re2.search(r"[가-힣]", _body[:600])) or "/rules/" in str(_f)
    if not _ours:
        continue
    for _m in _re2.finditer(r"(?:^|(?<=[\s`(]))/([a-z][a-z0-9-]{2,})\b(?![/.])", _body, _re2.MULTILINE):
        _name = _m.group(1)
        if _name not in loadable and _name not in _BUILTIN_SLASH:
            _line = _body.count("\n", 0, _m.start()) + 1
            _ctx = _body[max(0, _m.start() - 80):_m.start() + 80].replace("\n", " ")
            if _re2.search(_EXEMPT_CTX, _ctx):
                continue
            _ref_issues.append(f"{_rel}:{_line}: 미로드 스킬 '/{_name}' 참조")
if _ref_issues:
    for _item in sorted(set(_ref_issues))[:12]:
        print(f" {WARN} {_item}")
    issues += 1
else:
    print(f" {OK} 스킬/rules 참조 대상 전부 로드 가능 (스킬·워크플로 {len(loadable)}개 기준)")

# 4. plugins / statusline / guardrail
section("plugins / config")
for name, on in (cfg.get("enabledPlugins", {}) or {}).items():
    print(f" {INFO} {name} ({'버전 미핀' if on is True else on})")
if "statusLine" not in cfg:
    print(f" {WARN} statusline 미설정")
    issues += 1
else:
    print(f" {OK} statusline 설정됨")
has_guardrail = any("guardrail" in h.get("command", "")
                    for g in cfg.get("hooks", {}).get("PreToolUse", []) for h in g.get("hooks", []))
print(f" {OK if has_guardrail else WARN} PreToolUse guardrail {'활성' if has_guardrail else '미설정'}")
issues += 0 if has_guardrail else 1

# 4b. sandbox 상태 (활성인데 deps 부재 = fail-closed로 전 Bash 차단 위험 — 무음 방지, 2026-07-03)
import shutil
sb = cfg.get("sandbox") or {}
if sb.get("enabled"):
    missing = [t for t in ("bwrap", "socat") if not shutil.which(t)]
    if missing:
        print(f" {WARN} sandbox 활성인데 deps 부재: {', '.join(missing)} — failIfUnavailable={sb.get('failIfUnavailable')} (true면 전 Bash 차단). `sudo apt-get install -y {' '.join(missing)}`")
        issues += 1
    else:
        aw = (sb.get("filesystem") or {}).get("allowWrite", [])
        print(f" {OK} sandbox 활성 (bwrap+socat 존재, allowWrite {len(aw)}경로, failIfUnavailable={sb.get('failIfUnavailable')})")
else:
    print(f" {INFO} sandbox 미설정 (블랭킷 Bash는 guardrail만 방어 — OS경계 원하면 sandbox.enabled)")

# 5. 누적물
section("accumulation")
councils = list((CC / "council").glob("*/")) if (CC / "council").exists() else []
print(f" {INFO} council 폴더 {len(councils)}개" + (" -> prune 검토" if len(councils) > 30 else ""))
wl = CC / "worklog"
if wl.exists():
    n, m = mem_stat(wl)
    print(f" {INFO} worklog {n}개 (마지막 {age(m)})")

# 6. 런타임 버전 (이식 검증·기록)
section("versions")
for name, args in [("claude", ["claude", "--version"]), ("codex", ["codex", "--version"]),
                   ("node", ["node", "--version"]), ("python", ["python3", "--version"])]:
    v = ver(name, args)
    print(f" {INFO if v else WARN} {name}: {v or '없음'}")

print("\n" + "-" * 50)
print(f"{'PASS 이상 없음' if issues == 0 else f'CHECK 점검필요 {issues}건'}\n")
