#!/usr/bin/env python3
"""subagent-log.py — SubagentStop 훅 (observability). 서브에이전트 완료를 로그에 기록만(차단 안 함).
stdin: SubagentStop JSON (agent_type/agent_id 등 공통 필드). 출력: $COMMAND_CENTER/logs/subagents.log.
"""
import json
import os
import sys
import time

try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(0)

at = d.get("agent_type") or d.get("subagent_type") or "?"
aid = d.get("agent_id") or ""
try:
    cc = os.environ.get("COMMAND_CENTER") or os.path.join(os.path.expanduser("~"), "main")
    log = os.path.join(cc, "logs", "subagents.log")
    os.makedirs(os.path.dirname(log), exist_ok=True)
    if os.path.exists(log) and os.path.getsize(log) > 512_000:  # 로테이션: 최근 5000줄만 보존
        with open(log) as f:
            tail = f.readlines()[-5000:]
        with open(log, "w") as f:
            f.writelines(tail)
    with open(log, "a") as f:
        f.write(f"{int(time.time())}\t{at}\t{aid}\n")
except Exception:
    pass
sys.exit(0)
