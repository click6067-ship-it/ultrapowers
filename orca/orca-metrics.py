#!/usr/bin/env python3
"""Orca 운영 계측 스냅샷 v0 — 2주 판정(projects/orca-2w-measurement.md)용 데이터.

orchestration 이력에서 일 단위 카운트를 뽑아 logs/orca-metrics.jsonl 에
append한다(gitignore 영역 — 로컬 축적). 하루 여러 번 실행해도 안전(스냅샷마다
타임스탬프 행 추가; 판정 시 일별 최종값 사용).

주의: Claude 세션에서는 샌드박스 밖 실행 (orca-ide socket).
"""

from __future__ import annotations

import json
import os
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ORCA = os.environ.get("ORCA_CLI_COMMAND", "orca-ide")
OUT = Path.home() / "main/logs/orca-metrics.jsonl"


def orca_json(args: list[str]) -> dict:
    proc = subprocess.run(
        [ORCA, *args, "--json"], capture_output=True, text=True, timeout=60
    )
    proc.check_returncode()
    return json.loads(proc.stdout)


def main() -> None:
    tasks = orca_json(["orchestration", "task-list", "--brief"])["result"]["tasks"]
    status_counts = Counter(t["status"] for t in tasks)
    today = datetime.now(timezone.utc).date().isoformat()
    created_today = sum(
        1 for t in tasks if (t.get("created_at") or "").startswith(today)
    )
    completed_today = sum(
        1 for t in tasks if (t.get("completed_at") or "").startswith(today)
    )
    terminals = orca_json(["terminal", "list"])["result"]["terminals"]
    snapshot = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tasks_total": len(tasks),
        "tasks_by_status": dict(status_counts),
        "tasks_created_today_utc": created_today,
        "tasks_completed_today_utc": completed_today,
        "terminals_open": len(terminals),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(snapshot, ensure_ascii=False) + "\n")
    print(json.dumps(snapshot, ensure_ascii=False))


if __name__ == "__main__":
    main()
