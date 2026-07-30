#!/usr/bin/env python3
"""skill_usage_log_test.py — skill-usage-log.py 스모크 (wired=tested). 밀폐: COMMAND_CENTER=tmp."""
import json
import os
import subprocess
import sys
import tempfile

G = os.path.join(os.path.dirname(os.path.abspath(__file__)), "skill-usage-log.py")


def run(payload, cc):
    return subprocess.run(
        ["python3", G], input=payload, capture_output=True, text=True,
        env={**os.environ, "COMMAND_CENTER": cc},
    ).returncode


fails = 0
with tempfile.TemporaryDirectory() as cc:
    tsv = os.path.join(cc, "system", "state", "skill-usage.tsv")

    # 1) 정상 기록
    rc = run(json.dumps({"tool_input": {"skill": "vcheck"}}), cc)
    ok = rc == 0 and os.path.exists(tsv) and open(tsv).read().strip().endswith("\tvcheck")
    fails += 0 if ok else 1
    print(f"  [{'OK' if ok else 'FAIL'}] 기록: rc={rc} tsv={'있음' if os.path.exists(tsv) else '없음'}")

    # 2) append (2회째)
    run(json.dumps({"tool_input": {"skill": "kickoff"}}), cc)
    lines = open(tsv).read().strip().splitlines()
    ok = len(lines) == 2 and lines[1].endswith("\tkickoff")
    fails += 0 if ok else 1
    print(f"  [{'OK' if ok else 'FAIL'}] append: {len(lines)}줄")

    # 3) 깨진 입력·빈 스킬 — 항상 exit 0, 기록 없음
    ok = run("not-json", cc) == 0 and run(json.dumps({"tool_input": {}}), cc) == 0
    ok = ok and len(open(tsv).read().strip().splitlines()) == 2
    fails += 0 if ok else 1
    print(f"  [{'OK' if ok else 'FAIL'}] fail-open: 깨진 입력에도 rc0·미기록")

print("PASS" if fails == 0 else f"FAIL {fails}건")
sys.exit(1 if fails else 0)
