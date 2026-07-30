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
if canon.exists():
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
else:
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
    txt = gclaude.read_text()
    refd = set(_re.findall(r'rules/([a-z0-9-]+)\.md', txt))
    present = {p.stem for p in rules_dir.glob("*.md")} if rules_dir.exists() else set()
    missing = refd - present
    if missing:
        print(f" {WARN} CLAUDE.md가 참조하는 rules 부재: {', '.join(sorted(missing))}")
        issues += 1
    else:
        print(f" {OK} rules {len(present)}개, CLAUDE.md 참조 {len(refd)}개 전부 실재")

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

# 7. 문서-현실 drift (2026-07-03 감사 클래스 — 문서가 시스템 상태를 거짓 기술)
section("docs-reality drift")
drift_checks = []
main_claude = CC / "CLAUDE.md"
if main_claude.exists() and (CC / "worklog").exists() and "제거됨 (2026-05-27)" in main_claude.read_text():
    drift_checks.append("CLAUDE.md: worklog '제거됨' 서술 vs 폴더 라이브 (2026-06-28 '유지' 결정 미반영)")
sys_md = CC / "system/SYSTEM.md"
if sys_md.exists() and "obsidian/wiki" in sys_md.read_text().lower():
    drift_checks.append("SYSTEM.md: 폐기된 obsidian 경로가 기본값으로 잔존")
arch_md = CC / "system/ARCHITECTURE.md"
allow_rules = (cfg.get("permissions", {}) or {}).get("allow", [])
if arch_md.exists() and "Bash" in allow_rules and "블랭킷" not in arch_md.read_text():
    drift_checks.append("ARCHITECTURE.md: 권한 서술이 블랭킷 Bash 현실을 미반영")
hook_cmds = " ".join(h.get("command", "") for gs in cfg.get("hooks", {}).values() for g in gs for h in g.get("hooks", []))
if sys_md.exists() and "techreport-autopush" in hook_cmds and "techreport-autopush" not in sys_md.read_text():
    drift_checks.append("SYSTEM.md: 라이브 SessionEnd 훅 techreport-autopush 미문서화")
for d in drift_checks:
    print(f" {WARN} {d}")
issues += len(drift_checks)
if not drift_checks:
    print(f" {OK} 알려진 drift 패턴 없음")

# 8. 죽은/중복 권한 규칙 (블랭킷 Bash 아래 개별 Bash 규칙 = 사문)
section("permission rules")
for label, spath in (("settings.json", HOME / ".claude/settings.json"), ("settings.local.json", HOME / ".claude/settings.local.json")):
    try:
        rules = (json.loads(spath.read_text()).get("permissions", {}) or {}).get("allow", []) if spath.exists() else []
    except Exception:
        rules = []
    dead = [r for r in rules if r.startswith("Bash(")] if ("Bash" in allow_rules) else []
    if dead:
        print(f" {WARN} {label}: 블랭킷 Bash 아래 죽은 개별 규칙 {len(dead)}개")
        issues += 1
    elif rules:
        print(f" {OK} {label}: 규칙 {len(rules)}개 (사문 없음)")

# 9. 훅 크래시 무음 (>/dev/null로 에러 증발 + 로그 부재)
# 예외: Orca 에이전트 브리지(.orca/agent-hooks/)는 페인 밖에서 조용히 no-op하는 게 계약 — 무음이 의도(2026-07-26, 오탐 10건 소음이 진짜 회귀를 묻는 문제로 화이트리스트)
section("hook observability")
muted = [h.get("command", "")[:60] for gs in cfg.get("hooks", {}).values() for g in gs for h in g.get("hooks", []) if ">/dev/null" in h.get("command", "") and ".orca/agent-hooks/" not in h.get("command", "")]
for m in muted:
    print(f" {WARN} 무음 훅: {m}")
issues += len(muted)
hooks_log = CC / "logs/hooks.log"
if not muted:
    print(f" {OK} 무음 훅 없음" + (f" (hooks.log {age(hooks_log.stat().st_mtime)})" if hooks_log.exists() else ""))
if hooks_log.exists():
    tail = hooks_log.read_text().splitlines()[-50:]
    cutoff = dt.date.today() - dt.timedelta(days=2)
    errs = []
    for line in tail:
        if "ERROR" not in line and "FAIL" not in line:
            continue
        try:
            event_date = dt.date.fromisoformat(line[:10])
        except ValueError:
            event_date = dt.date.today()  # 날짜 없는 새 오류는 fail-closed
        if event_date >= cutoff:
            errs.append(line)
    if errs:
        print(f" {WARN} hooks.log 48시간 내 에러 {len(errs)}건 (마지막: {errs[-1][:70]})")
        issues += 1

# 10. worklog 캡처 품질 (하니스 태그를 프롬프트로 긁는 버그)
section("worklog capture")
# 러너가 *실제로 실행하는* 경로를 본다 — 2026-07-29 소유권 정합: 러너 실행 정본을
# 라이브 ~/.claude/hooks/ 로 일원화했으므로(독트린: 정본=~/.claude, dotclaude=미러) 그쪽을 본다.
ses_py = HOME / ".claude/hooks/session-end-summary.py"
if ses_py.exists():
    if "local-command-caveat" in ses_py.read_text():
        print(f" {OK} 하니스 태그 필터 있음")
    else:
        print(f" {WARN} session-end-summary.py: 하니스 태그(<local-command-caveat> 등) 미필터 — 프롬프트 캡처 오염")
        issues += 1

# 11. fan-out cap 존재 (워크플로 검증 폭주 방지 — council-research 35에이전트 교훈)
section("workflow fan-out caps")
for wf, marker in (("council-research.js", "TOPN"), ("repo-audit.js", "TOPN")):
    p = HOME / ".claude/workflows" / wf
    if p.exists():
        if marker in p.read_text():
            print(f" {OK} {wf}: cap 있음")
        else:
            print(f" {WARN} {wf}: verify fan-out cap 없음 — 폭주 가능")
            issues += 1

# 12. 활성 plugin hooks 인벤토리 + 변화 감지
section("plugin hooks inventory")
state_p = CC / "system/.doctor-state.json"
state = {}
try:
    state = json.loads(state_p.read_text()) if state_p.exists() else {}
except Exception:
    state = {}
inv = {}
plug_root = HOME / ".claude/plugins"
try:
    installed = (
        json.loads((plug_root / "installed_plugins.json").read_text()).get("plugins", {})
        if (plug_root / "installed_plugins.json").exists()
        else {}
    )
except Exception:
    installed = {}
enabled_plugins = {
    name for name, enabled in (cfg.get("enabledPlugins", {}) or {}).items() if enabled
}
ver_map = {}
for name in sorted(enabled_plugins):
    rows = installed.get(name) or []
    row = rows[-1] if isinstance(rows, list) and rows else {}
    version = row.get("version", "?") if isinstance(row, dict) else "?"
    install_path = Path(row.get("installPath", "")) if isinstance(row, dict) else Path()
    ver_map[name] = version
    hook_file = install_path / "hooks/hooks.json" if str(install_path) else None
    if hook_file and hook_file.is_file():
        try:
            events = sorted(json.loads(hook_file.read_text()).get("hooks", {}).keys())
        except Exception:
            events = ["<parse-fail>"]
    else:
        events = []
    inv[name] = events
    print(f" {INFO} {name} {version}: {','.join(events) if events else 'hooks 없음'}")
if "vercel@claude-plugins-official" in enabled_plugins:
    telemetry_off = (cfg.get("env") or {}).get("VERCEL_PLUGIN_TELEMETRY") == "off"
    print(f" {OK if telemetry_off else WARN} Vercel plugin telemetry {'off' if telemetry_off else '명시적 opt-out 없음'}")
    issues += 0 if telemetry_off else 1
snap = {"hooks": inv, "versions": ver_map}
if state.get("plugins") and state["plugins"] != snap:
    print(f" {WARN} plugin hooks/버전 변화 감지 (이전 스냅샷 대비) — 검토 후 스냅샷 갱신됨")
    issues += 1
state["plugins"] = snap
try:  # 상태 저장은 best-effort — 읽기 전용 FS에서도 진단은 계속돼야 함(2026-07-03 Codex A4)
    state_p.write_text(json.dumps(state, ensure_ascii=False, indent=1))
except OSError:
    print(f" {INFO} 스냅샷 저장 skip (쓰기 불가 — 진단은 계속)")

# 13. 미러 durable (복사≠백업 — dirty·커밋 age 판정)
section("mirror durability")
try:
    dirty = subprocess.run(["git", "-C", str(CC), "status", "--porcelain", "--", "system/memory-snapshot"],
                           capture_output=True, text=True, timeout=10).stdout.strip()
    last_ts = subprocess.run(["git", "-C", str(CC), "log", "-1", "--format=%ct", "--", "system/memory-snapshot"],
                             capture_output=True, text=True, timeout=10).stdout.strip()
    hrs = (time.time() - int(last_ts)) / 3600 if last_ts else 9999
    if dirty:
        print(f" {WARN} memory-snapshot 미커밋 변경 {len(dirty.splitlines())}건 (마지막 커밋 {int(hrs)}h 전)")
        issues += 1
    elif hrs > 48 and any(True for _ in (HOME / '.claude/projects').glob('*/memory/*.md')):
        live_latest = max((f.stat().st_mtime for f in (HOME / '.claude/projects').glob('*/memory/*.md')), default=0)
        if time.time() - live_latest < hrs * 3600:
            print(f" {WARN} memory-snapshot 마지막 커밋 {int(hrs)}h 전 — 라이브가 더 최신")
            issues += 1
        else:
            print(f" {OK} 미러 커밋 최신 (라이브 변경 없음)")
    else:
        print(f" {OK} 미러 clean + 커밋 {int(hrs)}h 전")
except Exception as e:
    print(f" {WARN} 미러 durable 판정 실패: {e}")
    issues += 1

# 14. 기한 있는 미결 결정 (projects/*.md frontmatter decide_by + status: pending — 2026-07-26 냉정평가: "결정 안 하고 병행 유지가 진짜 과적")
section("pending decisions")
try:
    import datetime as _dt
    import re
    pend = []
    for f in sorted((CC / "projects").glob("*.md")):
        head = f.read_text(errors="ignore")[:400]
        m_by = re.search(r"^decide_by:\s*(\d{4}-\d{2}-\d{2})", head, re.M)
        m_st = re.search(r"^status:\s*(\S+)", head, re.M)
        if m_by and m_st and m_st.group(1) == "pending":
            due = _dt.date.fromisoformat(m_by.group(1))
            days = (due - _dt.date.today()).days
            if days < 0:
                print(f" {WARN} {f.name}: 결정 기한 {abs(days)}일 초과 (decide_by {due}) — 결정하거나 기한 갱신")
                issues += 1
            else:
                pend.append(f"{f.name}(D-{days})")
    if pend:
        print(f" {INFO} 대기 중 결정: {' · '.join(pend)}")
    elif not any((CC / 'projects').glob('*.md')):
        print(f" {INFO} projects/ 없음")
    else:
        print(f" {OK} 기한 초과 미결 결정 없음")
except Exception as e:
    print(f" {WARN} pending decisions 판정 실패: {e}")

# 6. 런타임 버전 (이식 검증·기록)
section("versions")
for name, args in [("claude", ["claude", "--version"]), ("codex", ["codex", "--version"]),
                   ("node", ["node", "--version"]), ("python", ["python3", "--version"])]:
    v = ver(name, args)
    print(f" {INFO if v else WARN} {name}: {v or '없음'}")

print("\n" + "-" * 50)
print(f"{'PASS 이상 없음' if issues == 0 else f'CHECK 점검필요 {issues}건'}\n")
