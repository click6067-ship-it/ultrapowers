#!/usr/bin/env python3
"""guardrail.py — PreToolUse 정책 훅 (deny-by-policy).

치명적·비가역 작업만 차단(exit 2), 나머지 자율 허용(exit 0).
- shlex 토큰화(따옴표: rm -rf "$HOME"), 세그먼트 첫 토큰 기준(문자열 *언급*은 미차단 — 자율성 보존)
- 단·롱 플래그 모두(`-rf`, `--recursive --force`), 확장 홈/시스템 루트 타깃 인식
- `bash -c '...'` 내부 재귀 검사(우회 차단)
guardrail은 *방어선이지 샌드박스가 아니다* — 정상작업을 막지 않는 선에서 최악만 거른다.
stdin: PreToolUse JSON {tool_input:{command}}. 차단은 $COMMAND_CENTER/logs/guardrail.log 기록.

실패 모드 비대칭 (문서화 — 2026-07-03 감사):
- 스크립트 *내부* 크래시 → exit 1 (PreToolUse 비차단 에러) = fail-open: 명령은 통과.
- 스크립트 *파일 부재* → python3가 exit 2 = PreToolUse 차단 = fail-closed: 모든 Bash 차단.
  (이식 시 경로 깨지면 전 Bash가 막히는 쪽으로 실패 — 안전하지만 시끄러움. doctor의 hooks 체크가 탐지.)
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


# ── 크리덴셜 누출 방어 (2026-07-29 2백본 감사) ──────────────────────────────
# 왜: CLAUDE.md의 최고 스테이크 규칙(키 파일 Read 금지·값 stdout 금지·git add -A 금지)에
# 기계 집행이 0이었다. permissions.deny의 Read(...)는 Read 툴만 막고 Bash는 통째 allow라
# `cat ~/.secrets/...`가 무방비였다. 승인된 경로(source 주입·sha256 지문)는 통과시킨다.
_SECRET_PATH_RE = re.compile(
    r'(^|/)\.secrets(/|$)'
    r'|(^|/)\.env($|\.)'
    r'|api[ _-]?keys?[^/]*$'
    r'|(^|/)\.credentials\.json$'
    r'|(^|/)auth\.json$'
    r'|(^|/)id_rsa'
    r'|\.pem$', re.I)
_SECRET_SAFE_RE = re.compile(r'\.env\.(example|sample|template|dist)$', re.I)
# 내용을 stdout·다른 파일로 흘리는 명령만. source/./sha256sum/stat/ls/chmod는 승인 경로라 제외.
_DUMP_CMDS = {"cat", "bat", "less", "more", "head", "tail", "nl", "tac", "strings", "xxd",
              "od", "hexdump", "base64", "cp", "scp", "rsync", "tee",
              "grep", "egrep", "fgrep", "rg", "awk", "sed", "cut"}
_CRED_VAR_RE = re.compile(
    r'\$\{?[A-Za-z_]*(KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL)[A-Za-z0-9_]*\}?', re.I)
_CRED_NAME_RE = re.compile(r'^[A-Za-z_]*(KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL)', re.I)


# 패턴 인자를 받는 검색계 — 첫 인자가 파일이 아니라 검색어라, 크리덴셜 '이름'을 문서에서
# 찾는 read-only 감사(grep -rn api-keys …)가 오탐된다(2026-07-29 실측). 이들은 토큰이
# 실존 파일/디렉토리로 해석될 때만 차단한다. cat/cp류는 기존대로 이름만으로 차단.
_PATTERN_CMDS = {"grep", "egrep", "fgrep", "rg", "sed", "awk"}


def is_secret_path(t):
    s = t.strip('"\'')
    if _SECRET_SAFE_RE.search(s):
        return False
    return bool(_SECRET_PATH_RE.search(s))


def resolves_to_real_path(t):
    s = os.path.expandvars(os.path.expanduser(t.strip('"\'')))
    try:
        return os.path.exists(s)
    except Exception:
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
        cc = os.environ.get("COMMAND_CENTER") or os.path.join(HOMEDIR, "main")
        log = os.path.join(cc, "logs", "guardrail.log")
        os.makedirs(os.path.dirname(log), exist_ok=True)
        if os.path.exists(log) and os.path.getsize(log) > 512_000:  # 로테이션: 최근 2000줄만 보존
            with open(log) as f:
                tail = f.readlines()[-2000:]
            with open(log, "w") as f:
                f.writelines(tail)
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
        # env/printenv 단독 = 환경변수 전체 덤프. 아래 wrapper 소비에 먹히므로 여기서 먼저 본다.
        bare = [t for t in toks
                if not re.match(r'^[A-Za-z_][A-Za-z0-9_]*=', t) and not t.startswith("-")]
        if bare and bare[0] in ("env", "printenv"):
            if len(bare) == 1:
                block("환경변수 전체 덤프 — 크리덴셜 값이 stdout에 실린다")
            if bare[0] == "printenv" and any(_CRED_NAME_RE.match(a) for a in bare[1:]):
                block("크리덴셜 환경변수 값 출력 — 확인은 SHA256 지문으로")
        i = 0
        while i < len(toks) and re.match(r'^[A-Za-z_][A-Za-z0-9_]*=', toks[i]):
            i += 1
        # wrapper 다중 체인 반복 소비 (sudo env rm / time command rm 등 — 한 겹만 벗기면 우회됨, 2026-07-03 Codex A2)
        while i < len(toks) and toks[i] in ("sudo", "env", "command", "time", "nice", "ionice", "xargs", "doas", "stdbuf", "setsid", "nohup"):
            i += 1
            while i < len(toks) and (re.match(r'^[A-Za-z_]\w*=', toks[i]) or toks[i].startswith('-')):
                i += 1
        if i >= len(toks):
            continue
        c0 = toks[i]
        args = toks[i + 1:]
        if c0 in _DUMP_CMDS:
            hits = [t for t in args if is_secret_path(t)]
            if c0 in _PATTERN_CMDS:
                hits = [t for t in hits if resolves_to_real_path(t)]
            if hits:
                block("크리덴셜 파일 내용 노출·복사 — 값 확인은 SHA256 지문으로 (주입은 source)")
        if c0 in ("echo", "printf") and _CRED_VAR_RE.search(seg):
            block("크리덴셜 환경변수 값 stdout 출력")
        # F-1 (2026-07-31): curl/wget 크리덴셜 노출·탑재. 스코프 정밀 —
        # (a) verbose류(-v/-i/--trace*)+크리덴셜 변수 = 요청 헤더의 실값이 출력에 찍힘
        # (b) 시크릿 파일을 데이터로 탑재(@경로, --post-file 등) = 외부 전송
        # 일반 API 호출(curl -H "$KEY", verbose 없음)은 값이 컨텍스트에 안 찍히므로 허용 유지.
        if c0 in ("curl", "wget"):
            verbose = any(a in ("-v", "--verbose", "-i", "--include") or a.startswith("--trace")
                          for a in args)
            if verbose and _CRED_VAR_RE.search(seg):
                block("curl/wget verbose + 크리덴셜 변수 — 헤더 실값이 출력에 찍힌다 (값 확인은 SHA256 지문)")
            for t in args:
                cand = t[1:] if t.startswith("@") else t
                # 파일-형 토큰만: @경로(curl 데이터 문법) 또는 실존 경로 — 헤더 문자열의
                # "API_KEY" 오탐 방지 (allow: curl -H "Bearer $OPENAI_API_KEY")
                if is_secret_path(cand) and (t.startswith("@") or resolves_to_real_path(cand)):
                    block("curl/wget에 시크릿 파일 탑재 — 크리덴셜 외부 전송 금지")
        if c0 == "git" and "add" in args:
            gi = args.index("add")
            if any(a in ("-A", "--all", ".", ":/") for a in args[gi + 1:]):
                block("git add -A/. — 의도한 경로만 stage (pitfalls)")
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
        elif c0 == "git" and "push" in args:
            # +refspec force 형태 (git push origin +main) — force 플래그 없이 강제 푸시
            if any(re.match(r'^\+\S*\b(main|master)\b', t) for t in args):
                block("main/master +refspec force-push")
            if re.search(r'--force(-with-lease|-if-includes)?\b|(^|\s)-f(\s|$)', seg):
                if re.search(r'\b(main|master)\b', seg):
                    block("main/master force-push")
                # bare force-push (브랜치 무명시) — 현재 브랜치가 main/master일 수 있어 보호 우회 구멍.
                # remote+refspec 둘 다 명시한 force만 통과 (피처 브랜치 force는 명시로 가능).
                rest = [t for t in args[args.index("push") + 1:] if not t.startswith("-")]
                if len(rest) < 2:
                    block("bare force-push (원격·브랜치 명시 없이 -f — main/master 보호 우회 가능)")
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
