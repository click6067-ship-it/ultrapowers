#!/usr/bin/env python3
"""skill-usage-log.py — PreToolUse[Skill] 계측 훅 (2026-07-29 sandbag 감사 후속).

스킬 실행을 $COMMAND_CENTER/system/state/skill-usage.tsv 에 `epoch<TAB>스킬명`으로 기록만 한다.
왜: 언급 grep은 실행의 상한 추정치라 저사용 스킬(hallmark·spec-decompose 등)의 강등/유지
판단 근거가 못 된다 — 30일 실행 실측 후 판정하기로 결정(2026-07-29). 판단·차단 없음,
어떤 실패에도 exit 0 (계측이 작업을 막으면 안 된다). 한계: Workflow 툴로 도는 워크플로
스킬(council-research 등)은 Skill 툴을 안 거치므로 여기 안 잡힌다.
"""
import json
import os
import sys
import time


def main():
    try:
        d = json.load(sys.stdin)
        ti = d.get("tool_input") or {}
        name = (ti.get("skill") or "").strip() if isinstance(ti, dict) else ""
        if not name:
            return
        cc = os.environ.get("COMMAND_CENTER") or os.path.expanduser("$COMMAND_CENTER")
        state = os.path.join(cc, "system", "state")
        os.makedirs(state, exist_ok=True)
        with open(os.path.join(state, "skill-usage.tsv"), "a", encoding="utf-8") as f:
            f.write(f"{int(time.time())}\t{name}\n")
    except Exception:
        pass


main()
sys.exit(0)
