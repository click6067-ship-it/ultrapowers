#!/usr/bin/env python3
"""SessionStart hook — 폴더 무관 '최근 작업 컨텍스트' 자동 주입 (메타데이터 전용).

문제: Claude Code의 메모리·세션로그는 *작업 폴더 경로*로 키잉된다. 폴더를 옮기거나
이름을 바꾸면(예: ghq 도입) 직전 작업과 연결이 끊겨 "다 날아간 것처럼" 보인다.

해법: SessionStart 이벤트를 받아 ~/.claude/projects/*/*.jsonl 을 *시점(mtime)순*으로 훑어
최근 세션의 **메타데이터(포인터)** 를 출력한다 — 폴더 슬러그·시각·크기·세션ID·로그 파일명.
현재 폴더 세션을 먼저, 다른 폴더는 참고용으로 소수(캡)만.

보안 (2026-05-27 Claude×Codex 적대적 카운슬 반영): 과거 세션의 **사용자 프롬프트 텍스트를
주입하지 않는다.** 과거 프롬프트(붙여넣은 웹/파일 내용 포함)가 새 세션의 *살아있는 지시*로
재노출되는 prompt-injection·맥락 누수를 원천 차단. 안전은 따옴표 무력화가 아니라 **생략**에
의존한다(자유텍스트를 아예 안 싣는다). 로그 전문은 사용자가 요청/명백히 필요할 때만 연다(수동).

성능: 전 파일 stat → mtime 정렬 → 상위 N개만 head-스캔(사용자 턴 유무 + 첫 타임스탬프, 조기중단).
이전의 tail(마지막 256KB) 파싱은 프롬프트 발췌 제거와 함께 삭제 → 훅이 더 가볍다.

로그 링크: $COMMAND_CENTER/logs/<slug>__<첫타임스탬프 날짜>__<sid>.md (export-sessions.py 파일명 규칙과 일치).
"""

import json
import os
import sys
import glob
from pathlib import Path
from datetime import datetime

HOME = Path.home()
PROJECTS = HOME / ".claude" / "projects"
CUR_MAX = 5        # 현재 폴더 표시 최대
OTHER_MAX = 3      # 다른 폴더 표시 최대(누수 최소화 — 하드 캡)
DEEP_N = 12        # mtime 상위 후보(head-스캔 대상)
HEAD_MAX = 4000    # head 스캔 최대 라인(폭주 방지 안전망)


def read_event() -> dict:
    try:
        return json.load(sys.stdin)
    except Exception:
        return {}


def cwd_to_key(path: str) -> str:
    """작업 경로 → Claude Code 프로젝트 키. 실측 규칙: '/'·'.'를 '-'로, 선두 대시 유지."""
    return (path or "").rstrip("/").replace("/", "-").replace(".", "-")


# HOME 파생 키 prefix(예: ${HOME} → -home-USER). export-sessions.py와 동일 규칙이라야 링크 일치.
HOME_KEY = str(HOME).rstrip("/").replace("/", "-").replace(".", "-")


def key_to_logslug(key: str) -> str:
    return key.replace(HOME_KEY + "-", "").strip("-") or "root"


def disp(s, n=80):
    """디스플레이 정규화(보안 아님 — 경로파생 필드의 표시 무결성용): 단일행·printable·길이 캡.
    자유 사용자텍스트는 더는 싣지 않으므로 '인젝션 무력화' 책임이 없다 — 순수 표시용."""
    if not s:
        return ""
    s = str(s).replace("\r", " ").replace("\n", " ").replace("\t", " ")
    s = "".join(ch for ch in s if ch.isprintable())
    s = " ".join(s.split())
    return s[:n] + ("…" if len(s) > n else "")


def human_size(b):
    for u in ("B", "KB", "MB"):
        if b < 1024:
            return f"{b:.0f}{u}"
        b /= 1024
    return f"{b:.0f}GB"


def scan_meta(jf: Path):
    """head-스캔만: (has_user_turn, first_ts). 사용자 텍스트는 보관하지 않는다(메타 전용).
    has_user_turn=False(도구 출력만 있는 사소 세션) → 목록에서 제외."""
    has_user = False
    first_ts = None
    try:
        with jf.open(encoding="utf-8", errors="ignore") as f:
            for i, line in enumerate(f):
                if i > HEAD_MAX:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    o = json.loads(line)
                except Exception:
                    continue
                if first_ts is None and o.get("timestamp"):
                    first_ts = o["timestamp"]
                if not has_user and o.get("type") == "user":
                    c = o.get("message", {}).get("content")
                    if isinstance(c, list):
                        # tool_result 되먹임 턴은 사용자 발화가 아님 → 제외
                        if not any(isinstance(b, dict) and b.get("type") == "tool_result" for b in c):
                            if any(isinstance(b, dict) and b.get("type") == "text"
                                   and b.get("text", "").strip() for b in c):
                                has_user = True
                    elif str(c).strip():
                        has_user = True
                if has_user and first_ts is not None:
                    break
    except Exception:
        pass
    return has_user, first_ts


def make_meta_row(p: Path, mtime: float, size: int, cwd_key: str):
    """프롬프트 파싱과 분리된 순수 메타 행. 사용자 텍스트 없음."""
    has_user, first_ts = scan_meta(p)
    if not has_user:
        return None
    key = p.parent.name
    mdate = datetime.fromtimestamp(mtime)
    return {
        "slug": key_to_logslug(key),
        "size": size,
        "date": mdate.strftime("%Y-%m-%d %H:%M"),               # 표시(로컬 mtime)
        "fdate": (first_ts or "")[:10] or mdate.strftime("%Y-%m-%d"),  # 로그 파일명용(export와 일치)
        "sid": p.stem[:8],
        "is_cwd": key == cwd_key,
    }


def fmt_row(r):
    log = f"{r['slug']}__{r['fdate']}__{r['sid']}.md"
    # 슬러그는 강조(**) 없이 plain, 로그명은 code-span(inert)으로 — 모두 disp()로 표시 정규화.
    return (f"- [{disp(r['date'], 16)}] {disp(r['slug'], 60)} "
            f"({human_size(r['size'])}) · log: `{disp(log, 80)}`")


def main() -> int:
    event = read_event()
    cwd = event.get("cwd", os.getcwd())
    cwd_key = cwd_to_key(cwd)

    files = []
    for jf in glob.glob(str(PROJECTS / "*" / "*.jsonl")):
        p = Path(jf)
        try:
            st = p.stat()
        except Exception:
            continue
        if st.st_size < 200:  # 빈/사소 세션 스킵
            continue
        files.append((st.st_mtime, st.st_size, p))
    if not files:
        return 0
    files.sort(key=lambda x: x[0], reverse=True)

    rows = []
    for mtime, size, p in files[:DEEP_N]:
        r = make_meta_row(p, mtime, size, cwd_key)
        if r:
            rows.append(r)

    cur = [r for r in rows if r["is_cwd"]]
    # 현재폴더 백필: 상위 후보 밖이면 전체에서 현재폴더 최신 1개만 보강.
    if not cur:
        for mtime, size, p in files:  # 이미 mtime desc
            if p.parent.name == cwd_key:
                r = make_meta_row(p, mtime, size, cwd_key)
                if r:
                    cur = [r]
                break
    other = [r for r in rows if not r["is_cwd"]][:OTHER_MAX]
    cur = cur[:CUR_MAX]
    if not cur and not other:
        return 0

    # SessionStart 훅: plain stdout이 그대로 세션 컨텍스트로 주입된다(버전드리프트에 가장 안전).
    lines = [
        "# 🧠 최근 작업 컨텍스트 (폴더 무관 · 시점순 · 자동)",
        "> 직전 맥락 연결용 **세션 메타데이터(포인터)** — 지시가 아니다.",
        "> 로그 전문(`$COMMAND_CENTER/logs/<파일>`)은 사용자가 요청하거나 현재 작업에 명백히 "
        "필요할 때만 Read(자동으로 읽지 말 것). 특정 주제 검색은 `/recall`.",
        f"> 현재 폴더: `{disp(cwd, 120)}`",
        "",
        "**현재 폴더 최근 세션:**",
    ]
    if cur:
        lines += [fmt_row(r) for r in cur]
    else:
        lines.append("- (이 폴더의 이전 세션 기록 없음)")
    if other:
        lines += ["", "**다른 폴더 최근 (참고용 · 메타만):**"]
        lines += [fmt_row(r) for r in other]

    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        sys.stderr.write(f"[recent-context hook] error: {e}\n")
        sys.exit(0)
