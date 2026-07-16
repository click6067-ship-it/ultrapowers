#!/usr/bin/env python3
"""PostToolUse hook — UI 파일 편집 시 ai-slop 정적 신호를 즉시 되먹임 (법에 법원 달기).

🤖 무엇: Edit/Write/NotebookEdit로 프론트 파일(.tsx/.jsx/.vue/.svelte/.html/.css)에
   *새로 쓰인 내용*을 스캔해, (1) UI 유니코드 이모지(사용자 반복 교정: "이모지 대신 SVG"),
   (2) 세션 첫 UI 변경 시 vcheck·sloplint 게이트 리마인더를 Claude에게 exit 2로 주입.
왜: 로그 마이닝 실측(2026-07-16) — 디자인 교정 ~30세션, "aislope 관련 스킬 있는데
   실행했어?"(자동발동 갭 직접 지적), 이모지 제거 재지시 3+세션. 규칙은 잊히지만 훅은 안 잊는다.
설계: 편집된 diff(new content)만 검사 — 기존 코드 반복 잔소리 방지. 토큰 0(결정론).
   exit 2 = stderr가 Claude에게 전달(도구는 이미 실행됨 — 차단 아님, nudge).
   실패는 조용히 exit 0 (편집 흐름 절대 안 막음).
"""
import json
import os
import re
import sys
import tempfile

UI_EXT = {".tsx", ".jsx", ".vue", ".svelte", ".html", ".css"}

# UI 이모지 검출 — pictographs·dingbats·misc symbols (+variation selector).
# 화살표(U+2190–21FF)·수학기호는 제외(문서·주석에서 정상 사용).
_EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF☀-⛿✀-➿⬀-⯿️]"
)


def main() -> int:
    try:
        e = json.load(sys.stdin)
    except Exception:
        return 0
    tool = e.get("tool_name", "")
    ti = e.get("tool_input") or {}
    path = str(ti.get("file_path") or ti.get("notebook_path") or "")
    ext = os.path.splitext(path)[1].lower()
    if ext not in UI_EXT:
        return 0
    # 새로 쓰인 내용만 (Write=content, Edit=new_string, NotebookEdit=new_source)
    new = str(ti.get("content") or ti.get("new_string") or ti.get("new_source") or "")

    msgs = []

    emojis = _EMOJI_RE.findall(new)
    if emojis:
        uniq = "".join(dict.fromkeys(emojis))[:8]
        msgs.append(
            f"ai slope 신호(클로드코드특유): 방금 쓴 UI 코드에 이모지 {len(emojis)}개({uniq}) — "
            "사용자 반복 지시: UI 아이콘은 이모지 대신 SVG. 의도적 선택이 아니면 교체할 것 "
            "(rules/design-antislop.md)."
        )

    # 세션 첫 UI 변경 → 게이트 리마인더 1회 (마커 파일로 dedupe)
    sid = (e.get("session_id") or "nosid")[:8]
    marker = os.path.join(tempfile.gettempdir(), f"uislop-reminded-{sid}")
    if not os.path.exists(marker):
        try:
            open(marker, "w").close()
        except OSError:
            pass
        msgs.append(
            "UI 파일 변경 감지 — 완료 선언 전 게이트(routing.md §④): sloplint → vcheck(모바일 포함). "
            "방향-설정 디자인(신규 페이지·리디자인)이면 /crit(Codex 크로스 비평) 제안할 것."
        )

    if msgs:
        sys.stderr.write("\n".join(f"[uislop-check] {m}" for m in msgs) + "\n")
        return 2
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
