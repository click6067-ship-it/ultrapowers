#!/usr/bin/env python3
"""Orca crew finalization checker v0 — 결정론 게이트의 실행형 (read-only).

orca-trio finalization 계약 중 기계 판정 가능한 검사를 실행하고
PASS / NOT_VERIFIED 를 낸다. merge/push/정리는 하지 않는다 (사용자 gate 소유).

검사: ① git fetch 후 ahead/behind ② tracked dirty가 허용목록뿐인지
③ orchestration open task 0 ④ 미읽음 lifecycle mail 0 ⑤ 임시(race/drill 등)
worktree 잔존 0. 어떤 검사도 실행 못 하면 PASS가 아니라 NOT_VERIFIED다.

주의: orca-ide 호출 때문에 Claude 세션에서는 샌드박스 밖에서 실행해야 한다.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

REPO = os.path.expanduser("~/main")
ORCA = os.environ.get("ORCA_CLI_COMMAND", "orca-ide")
# 사용자 소유로 확인된 장기 dirty 파일 — 이 목록 밖의 tracked 변경은 실패.
ALLOWED_DIRTY = {"system/openclaw-orca-charter.md"}
TRANSIENT_WORKTREE_MARKERS = ("race-cand", "drill-", "-tmp-")


def run(cmd: list[str], timeout: int = 60) -> tuple[int, str]:
    proc = subprocess.run(
        cmd, cwd=REPO, capture_output=True, text=True, timeout=timeout
    )
    # 선행 공백은 porcelain status 칼럼의 일부다 — 전체 strip은 첫 줄을 훼손한다.
    return proc.returncode, (proc.stdout + proc.stderr).rstrip("\n")


def orca_json(args: list[str]) -> dict:
    code, out = run([ORCA, *args, "--json"], timeout=60)
    if code != 0:
        raise RuntimeError(f"{ORCA} {' '.join(args)} failed: {out[:200]}")
    return json.loads(out)


def main() -> int:
    checks: list[tuple[str, bool, str]] = []

    def add(name: str, ok: bool, detail: str) -> None:
        checks.append((name, ok, detail))

    try:
        code, out = run(["git", "fetch", "--quiet", "origin"], timeout=120)
        add("fetch", code == 0, out[:120] or "ok")
        _, ahead = run(["git", "rev-list", "--count", "origin/master..master"])
        _, behind = run(["git", "rev-list", "--count", "master..origin/master"])
        add(
            "divergence",
            behind == "0",
            f"ahead={ahead} behind={behind}"
            + ("" if behind == "0" else " — behind>0이면 통합 전 divergence 판정 필요"),
        )
        _, status = run(["git", "status", "--porcelain"])
        tracked_dirty = [
            line[3:]
            for line in status.splitlines()
            if line and not line.startswith("??")
        ]
        unexpected = [p for p in tracked_dirty if p not in ALLOWED_DIRTY]
        add(
            "tracked-dirty",
            not unexpected,
            "허용 외 변경: " + (", ".join(unexpected) if unexpected else "없음"),
        )

        tasks = orca_json(["orchestration", "task-list", "--brief"])["result"]["tasks"]
        open_tasks = [
            t["id"] for t in tasks if t["status"] not in ("completed", "failed")
        ]
        add("open-tasks", not open_tasks, ", ".join(open_tasks) or "0")

        inbox = orca_json(["orchestration", "check", "--peek"])["result"]
        add("unread-mail", inbox.get("count", 0) == 0, f"count={inbox.get('count')}")

        worktrees = orca_json(["worktree", "list"])["result"]["worktrees"]
        transient = [
            w["id"]
            for w in worktrees
            if any(m in w["id"] for m in TRANSIENT_WORKTREE_MARKERS)
        ]
        add("transient-worktrees", not transient, ", ".join(transient) or "0")
    except Exception as exc:  # 어떤 검사든 실행 불능 = NOT_VERIFIED
        add("runner", False, f"검사 실행 실패: {exc}")

    all_ok = bool(checks) and all(ok for _, ok, _ in checks)
    for name, ok, detail in checks:
        print(f"{'✓' if ok else '✗'} {name}: {detail}")
    print("PASS" if all_ok else "NOT_VERIFIED")
    return 0 if all_ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
