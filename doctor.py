#!/usr/bin/env python3
"""doctor.py — Claude Code 시스템 헬스체크 + 이식 후 검증 (observability).

읽기 전용 진단. 손대지 않고 '지금 무엇이 어긋났나'만 보고한다.
점검: codex auth · 메모리 미러 drift · hooks 무결성 · plugins · 누적물 · 런타임 버전.
이식 가능: COMMAND_CENTER env(기본 ~/main)로 미러 위치 결정.

사용: python3 ~/main/system/doctor.py   (또는 deploy/install 끝에 자동 실행)
"""
import json
import os
import subprocess
import time
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


print("\nClaude Code system doctor\n" + "-" * 50)

# 1. Codex auth (kickoff 무성실패 방지)
section("codex auth")
v = ver("codex", ["codex", "login", "status"])
if v and "logged in" in v.lower():
    print(f" {OK} {v}")
else:
    print(f" {WARN} 로그인 확인 필요: {v or 'codex 없음'}")
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
                spath = cmd.replace("python3 ", "").replace("bash ", "").split()[0] if cmd else ""
                if spath.startswith("/") and not Path(spath).exists():
                    print(f" {WARN} {event}: 스크립트 없음 -> {spath}")
                    issues += 1
                else:
                    print(f" {OK} {event}: {Path(spath).name or cmd[:36]}")
except Exception as e:
    print(f" {WARN} settings.json 파싱 실패: {e}")
    issues += 1

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
