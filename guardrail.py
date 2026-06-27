#!/usr/bin/env python3
"""guardrail.py — PreToolUse 정책 훅 (deny-by-policy).

치명적·비가역 작업만 차단(exit 2), 나머지 자율 허용(exit 0).
- shlex 토큰화(따옴표: rm -rf "$HOME"), 세그먼트 첫 토큰 기준(문자열 *언급*은 미차단 — 자율성 보존)
- 단·롱 플래그 모두(`-rf`, `--recursive --force`), 확장 홈/시스템 루트 타깃 인식
- `bash -c '...'` 내부 재귀 검사(우회 차단)
guardrail은 *방어선이지 샌드박스가 아니다* — 정상작업을 막지 않는 선에서 최악만 거른다.
stdin: PreToolUse JSON {tool_input:{command}}. 차단은 ~/main/logs/guardrail.log 기록.
"""
import json
import os
import re
import shlex
import sys
import time

HOMEDIR = os.path.expanduser("~")
_SYS_ROOTS = {"/home", "/root", "/usr", "/etc", "/var", "/bin", "/boot", "/lib", "/sys", "/opt"}
_cmd_for_log = ""


def is_danger_target(t):
    s = t.rstrip("/").rstrip("*").rstrip("/")
    if s in ("", "/"):                 # /  ·  /*  ·  /
        return True
    if s in ("~", "$HOME", "${HOME}", HOMEDIR) or s in _SYS_ROOTS:
        return True
    # $HOME / ${HOME...} 파라미터 확장(:- :? % # 등)이 홈 루트로 펼쳐지는 형태 (서브디렉터리는 제외)
    if re.match(r'^\$\{?HOME([:%#?+=!^,/\-][^}]*)?\}?$', s):
        return True
    return False


def has_recursive(args):
    for a in args:
        if a in ("-r", "-R", "--recursive"):
            return True
        if re.match(r'^-[a-zA-Z]+$', a) and ("r" in a or "R" in a):
            return True
    return False


def has_force(args):
    for a in args:
        if a in ("-f", "--force"):
            return True
        if re.match(r'^-[a-zA-Z]+$', a) and "f" in a:
            return True
    return False


def block(why):
    try:
        log = os.path.expanduser("~/main/logs/guardrail.log")
        os.makedirs(os.path.dirname(log), exist_ok=True)
        with open(log, "a") as f:
            f.write(f"{int(time.time())}\t{why}\t{_cmd_for_log}\n")
    except Exception:
        pass
    print(f"BLOCKED by guardrail: {why} (치명적·비가역 — 의도면 직접 실행)", file=sys.stderr)
    sys.exit(2)


def toks_of(seg):
    try:
        return shlex.split(seg)
    except Exception:
        return seg.split()


def check(cmd, depth=0):
    if depth > 4:
        return
    for seg in re.split(r'&&|\|\||[;\n|]', cmd):
        toks = toks_of(seg)
        if not toks:
            continue
        i = 0
        while i < len(toks) and re.match(r'^[A-Za-z_][A-Za-z0-9_]*=', toks[i]):
            i += 1
        if i < len(toks) and toks[i] in ("sudo", "env", "command", "time", "nice", "ionice", "xargs", "doas"):
            i += 1
            while i < len(toks) and (re.match(r'^[A-Za-z_]\w*=', toks[i]) or toks[i].startswith('-')):
                i += 1
        if i >= len(toks):
            continue
        c0 = toks[i]
        args = toks[i + 1:]
        if c0 in ("bash", "sh", "zsh", "dash", "ksh") and "-c" in args:
            ci = args.index("-c")
            if ci + 1 < len(args):
                check(args[ci + 1], depth + 1)
            continue
        if c0 == "rm" and has_recursive(args) and has_force(args) and any(is_danger_target(t) for t in args):
            block("rm -rf 홈/루트/시스템")
        elif c0 == "mkfs" or c0.startswith("mkfs."):
            block("파일시스템 포맷(mkfs)")
        elif c0 == "dd" and any(re.match(r'of=/dev/(sd|nvme|hd|disk|mmcblk)', t) for t in args):
            block("디스크 직접 덮어쓰기(dd of=/dev/)")
        elif c0 == "chmod" and has_recursive(args) and any(t in ("777", "0777") for t in args) \
                and any(is_danger_target(t) for t in args):
            block("chmod -R 777 홈/루트")
        elif c0 == "git" and "push" in args \
                and re.search(r'--force\b|--force-with-lease\b|(^|\s)-f(\s|$)', seg) \
                and re.search(r'\b(main|master)\b', seg):
            block("main/master force-push")
    if re.search(r':\s*\(\s*\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:', cmd):
        block("fork bomb")


def main():
    global _cmd_for_log
    try:
        d = json.load(sys.stdin)
    except Exception:
        sys.exit(0)
    ti = d.get("tool_input") or {}
    cmd = ti.get("command", "") if isinstance(ti, dict) else ""
    if not cmd:
        sys.exit(0)
    _cmd_for_log = cmd
    check(cmd)
    sys.exit(0)


main()
