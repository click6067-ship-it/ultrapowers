#!/usr/bin/env python3
"""guardrail.py — PreToolUse 정책 훅 (deny-by-policy, 명령-위치 정밀).

치명적·비가역 작업만 차단(exit 2), 나머지 자율 허용(exit 0).
**문자열에 위험단어가 단순 언급된 경우는 차단하지 않는다** — 명령을 세그먼트로 쪼개
각 세그먼트의 *첫 토큰*이 실제 위험 명령일 때만 검사(false-positive 최소, 자율성 보존).
stdin: PreToolUse JSON {tool_name, tool_input:{command}}. 차단은 ~/main/logs/guardrail.log 기록.
"""
import json
import os
import re
import sys
import time

try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(0)

ti = d.get("tool_input") or {}
cmd = ti.get("command", "") if isinstance(ti, dict) else ""
if not cmd:
    sys.exit(0)

DANGER_TARGET = re.compile(r'^(/|~|\$HOME|/\*|~/?\*|\$HOME/?\*)$')


def block(why):
    try:
        log = os.path.expanduser("~/main/logs/guardrail.log")
        os.makedirs(os.path.dirname(log), exist_ok=True)
        with open(log, "a") as f:
            f.write(f"{int(time.time())}\t{why}\t{cmd}\n")
    except Exception:
        pass
    print(f"BLOCKED by guardrail: {why} (치명적·비가역 — 의도면 직접 실행)", file=sys.stderr)
    sys.exit(2)


# 세그먼트 분리(셸 구분자). 각 세그먼트의 첫 실제 명령만 검사.
for seg in re.split(r'&&|\|\||[;\n|]', cmd):
    toks = seg.strip().split()
    if not toks:
        continue
    i = 0
    # 선행 env VAR=val · sudo · env 건너뜀
    while i < len(toks) and re.match(r'^[A-Za-z_][A-Za-z0-9_]*=', toks[i]):
        i += 1
    if i < len(toks) and toks[i] in ("sudo", "env", "command", "time", "nice", "ionice"):
        i += 1
        while i < len(toks) and re.match(r'^[A-Za-z_][A-Za-z0-9_]*=', toks[i]):
            i += 1
    if i >= len(toks):
        continue
    c0 = toks[i]
    args = toks[i + 1:]
    flags = "".join(t[1:] for t in args if re.match(r'^-[a-zA-Z]+$', t))

    if c0 == "rm" and "r" in flags and "f" in flags:
        for t in args:
            if DANGER_TARGET.match(t):
                block("rm -rf 홈/루트/전역")
    elif c0 == "mkfs" or c0.startswith("mkfs."):
        block("파일시스템 포맷(mkfs)")
    elif c0 == "dd" and any(re.match(r'of=/dev/(sd|nvme|hd|disk|mmcblk)', t) for t in args):
        block("디스크 직접 덮어쓰기(dd of=/dev/)")
    elif c0 == "chmod" and "R" in flags and any(t in ("777", "0777") for t in args) \
            and any(DANGER_TARGET.match(t) for t in args):
        block("chmod -R 777 홈/루트")
    elif c0 == "git" and "push" in args and re.search(r'(--force\b|--force-with-lease\b|(^|\s)-f\b)', seg) \
            and re.search(r'\b(main|master)\b', seg):
        block("main/master force-push")

# 전체 문자열 검사(언급-오탐 위험 낮은 시그니처만)
if re.search(r':\s*\(\s*\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:', cmd):
    block("fork bomb")

sys.exit(0)
