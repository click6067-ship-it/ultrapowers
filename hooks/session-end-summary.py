#!/usr/bin/env python3
"""SessionEnd hook — 세션이 *실제로 종료*될 때 1회, worklog 디렉터리에 세션 마무리 요약을 남긴다.

왜 SessionEnd인가 (2026-05-27): Stop 훅은 매 턴(응답 종료)마다 발동 → 세션당 수십 개 스텁
양산(옛 worklog 버그, 439개 빈 템플릿). SessionEnd는 세션 종료(clear/logout/exit 등)에
*세션당 1회* 발동 → 마무리 1개. 이게 "모든 작업 후 자동 마무리"(니즈#6)의 올바른 자리.

동작: stdin의 SessionEnd 이벤트(session_id·transcript_path·cwd·reason)를 받아 transcript를
파싱 → 첫·마지막 프롬프트 + 도구호출/메시지 수 + 소요시간을 뽑아, worklog 폴더에
세션당 1개 markdown(파일명=날짜-세션ID8)으로 기록. 같은 세션 재발동 시 덮어씀(idempotent).
사소 세션(사용자 프롬프트<2)·SKIP 마커는 건너뜀. 실패해도 exit 0(세션 막지 않음).

주의: 하드 크래시/강제킬엔 SessionEnd가 안 뜰 수 있다 → 그 경우에도 전체대화는 Stop 훅의
export-sessions.py가 $COMMAND_CENTER/logs/에 매 턴 보존하므로 유실 없음(이 *요약*만 생략될 뿐).
"""
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# 이식성: WORKLOG_DIR env 우선, 없으면 COMMAND_CENTER/worklog (기본 $COMMAND_CENTER/worklog). 개인 경로 하드코딩 제거.
WORKLOG_DIR = Path(os.environ.get("WORKLOG_DIR") or (Path(os.environ.get("COMMAND_CENTER") or (Path.home() / "main")) / "worklog"))
SKIP_MARKER = WORKLOG_DIR / ".skip-once"  # touch 시 다음 자동기록 1회 건너뜀


def read_event() -> dict:
    try:
        return json.load(sys.stdin)
    except Exception:
        return {}


def parse_transcript(path):
    """(first_user, last_user, tool_calls, msg_count, first_ts, last_ts)."""
    first = last = first_ts = last_ts = None
    tools = msgs = 0
    if not path or not os.path.isfile(path):
        return first, last, tools, msgs, first_ts, last_ts
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                o = json.loads(line)
            except Exception:
                continue
            ts = o.get("timestamp")
            if ts:
                first_ts = first_ts or ts
                last_ts = ts
            t = o.get("type")
            if t == "user":
                c = o.get("message", {}).get("content")
                if isinstance(c, list):
                    # tool_result 되먹임 턴은 사용자 발화 아님
                    if any(isinstance(b, dict) and b.get("type") == "tool_result" for b in c):
                        continue
                    txt = " ".join(b.get("text", "") for b in c
                                   if isinstance(b, dict) and b.get("type") == "text").strip()
                else:
                    txt = str(c).strip()
                if txt:
                    if first is None:
                        first = txt
                    last = txt
                    msgs += 1
            elif t == "assistant":
                c = o.get("message", {}).get("content", [])
                if isinstance(c, list):
                    tools += sum(1 for b in c if isinstance(b, dict) and b.get("type") == "tool_use")
                msgs += 1
    return first, last, tools, msgs, first_ts, last_ts


def trunc(s, n=500):
    if not s:
        return ""
    s = s.replace("\r", " ").strip()
    return s if len(s) <= n else s[:n].rstrip() + " …"


def dur(a, b):
    try:
        fa = datetime.fromisoformat(a.replace("Z", "+00:00"))
        fb = datetime.fromisoformat(b.replace("Z", "+00:00"))
        m = int((fb - fa).total_seconds() // 60)
        return f"{m // 60}h{m % 60:02d}m" if m >= 60 else f"{m}m"
    except Exception:
        return "?"


def main() -> int:
    e = read_event()
    tp = e.get("transcript_path", "")
    cwd = e.get("cwd", os.getcwd())
    sid = e.get("session_id", "")
    reason = e.get("reason", "")

    first, last, tools, msgs, first_ts, last_ts = parse_transcript(tp)
    if not first or msgs < 2:   # 사소 세션 스킵
        return 0
    if SKIP_MARKER.exists():
        try:
            SKIP_MARKER.unlink()
        except Exception:
            pass
        return 0

    WORKLOG_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now()
    date = (first_ts or "")[:10] or now.strftime("%Y-%m-%d")
    sid8 = (sid or "nosid")[:8]
    out = WORKLOG_DIR / f"{date}-{sid8}.md"   # 세션당 1개(고정명) — 재발동 시 덮어씀
    title = trunc(first, 60).split("\n", 1)[0]

    body = f"""---
date: {date}
time: {now.strftime('%H:%M')}
tags: [worklog, auto, session-summary]
project:
status: wip
session_id: {sid}
cwd: {cwd}
end_reason: {reason}
tool_calls: {tools}
messages: {msgs}
duration: {dur(first_ts, last_ts)}
---

# {title}

## 한 일 (무엇을 했나)



## 결정·배운 점



## 다음 (이어서 할 것)



---

## 자동 캡처 (참고)
- 첫 프롬프트: {trunc(first, 300)}
- 마지막 프롬프트: {trunc(last, 300)}
- 도구호출 {tools} · 메시지 {msgs} · 소요 {dur(first_ts, last_ts)} · 종료사유 `{reason}`
- 작업 디렉토리: `{cwd}`
"""
    out.write_text(body, encoding="utf-8")
    try:
        out.chmod(0o600)   # 요약에 프롬프트 일부 포함 → 소유자만 읽기
    except OSError:
        pass
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as ex:
        sys.stderr.write(f"[session-end-summary] error: {ex}\n")
        sys.exit(0)
