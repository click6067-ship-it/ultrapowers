#!/usr/bin/env python3
"""Isolated smoke tests for hook entrypoints not covered by dedicated suites."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def run(
    command: list[str],
    payload: dict | None,
    env: dict[str, str],
    expected_codes: set[int] = {0},
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        input=json.dumps(payload) if payload is not None else None,
        text=True,
        capture_output=True,
        env=env,
        timeout=20,
    )
    if result.returncode not in expected_codes:
        raise AssertionError(
            f"{command[-1]} exited {result.returncode}: {result.stderr[:300]}"
        )
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="hook-smoke-") as raw:
        base = Path(raw)
        fake_home = base / "home"
        command_center = base / "command-center"
        tmpdir = base / "tmp"
        projects = fake_home / ".claude/projects/-tmp-work"
        projects.mkdir(parents=True)
        command_center.mkdir()
        tmpdir.mkdir()

        env = os.environ.copy()
        env.update(
            {
                "HOME": str(fake_home),
                "COMMAND_CENTER": str(command_center),
                "TMPDIR": str(tmpdir),
                "CC_TOAST": "0",
                "ORCA_AGENT_HOOK_ENDPOINT": "",
                "ORCA_AGENT_HOOK_PORT": "",
                "ORCA_AGENT_HOOK_TOKEN": "",
                "ORCA_PANE_KEY": "",
            }
        )
        python = sys.executable

        # Orca trio arm + deny must work without a live repo or Orca runtime.
        arm = run(
            [python, str(ROOT / "orca-trio-guard.py")],
            {
                "hook_event_name": "UserPromptSubmit",
                "session_id": "smoke-trio",
                "prompt": "orca trio 세팅",
            },
            env,
        )
        if "orca trio" not in arm.stdout.lower():
            raise AssertionError("orca-trio guard did not arm")
        deny = run(
            [python, str(ROOT / "orca-trio-guard.py")],
            {
                "hook_event_name": "PreToolUse",
                "session_id": "smoke-trio",
                "tool_name": "Agent",
                "cwd": str(base),
            },
            env,
        )
        if '"permissionDecision": "deny"' not in deny.stdout:
            raise AssertionError("orca-trio guard did not deny Agent")

        nudge = run(
            [python, str(ROOT / "skill-nudge.py")],
            {
                "hook_event_name": "UserPromptSubmit",
                "session_id": "smoke-nudge",
                "prompt": "로컬 서버 띄워",
            },
            env,
        )
        if "/serve" not in nudge.stdout:
            raise AssertionError("skill nudge did not emit /serve guidance")

        session = projects / "a1b2c3d4-session.jsonl"
        rows = [
            {
                "type": "user",
                "timestamp": "2026-07-30T00:00:00Z",
                "message": {
                    "content": [
                        {"type": "text", "text": "api_key=abcd1234 smoke input"}
                    ]
                },
            },
            {
                "type": "assistant",
                "timestamp": "2026-07-30T00:00:01Z",
                "message": {"content": [{"type": "text", "text": "done"}]},
            },
        ]
        session.write_text(
            "\n".join(json.dumps(row) for row in rows) + "\n" + (" " * 220),
            encoding="utf-8",
        )

        recent = run(
            [python, str(ROOT / "recent-context.py")],
            {"hook_event_name": "SessionStart", "cwd": "/tmp/work"},
            env,
        )
        if "최근 작업 컨텍스트" not in recent.stdout:
            raise AssertionError("recent-context emitted no metadata")

        exported = run(
            [python, str(ROOT / "export-sessions.py")],
            None,
            env,
        )
        readme = command_center / "logs/README.md"
        exported_logs = list((command_center / "logs").glob("*.md"))
        if exported.returncode != 0 or not readme.exists() or len(exported_logs) < 2:
            raise AssertionError("export-sessions produced no isolated archive")
        combined = "\n".join(path.read_text(encoding="utf-8") for path in exported_logs)
        if "abcd1234" in combined or "[REDACTED]" not in combined:
            raise AssertionError("export-sessions redaction failed")

        ui = run(
            [python, str(ROOT / "uislop-check.py")],
            {
                "hook_event_name": "PostToolUse",
                "session_id": "smoke-ui",
                "tool_name": "Write",
                "tool_input": {
                    "file_path": str(base / "view.tsx"),
                    "content": "export default function View(){return <div>ok</div>}",
                },
            },
            env,
            {2},
        )
        if "완료 선언 전 게이트" not in ui.stderr:
            raise AssertionError("uislop check emitted no completion gate")

        run(
            [python, str(ROOT / "subagent-log.py")],
            {
                "hook_event_name": "SubagentStop",
                "session_id": "smoke-subagent",
                "agent_id": "agent-smoke",
                "agent_type": "smoke",
                "cwd": str(base),
                "last_assistant_message": "token=abcd1234",
            },
            env,
        )
        subagent_log = command_center / "logs/subagents.jsonl"
        if not subagent_log.exists():
            raise AssertionError("subagent log was not written")
        if "abcd1234" in subagent_log.read_text(encoding="utf-8"):
            raise AssertionError("subagent log redaction failed")

        for bridge in (
            fake_home / ".orca/agent-hooks/codex-hook.sh",
            fake_home / ".orca/agent-hooks/claude-hook.sh",
        ):
            bridge.parent.mkdir(parents=True, exist_ok=True)
        # Execute the real bridge paths with endpoint variables cleared. They
        # must fail open without attempting a network request.
        for bridge in (
            Path("/home/click/.orca/agent-hooks/codex-hook.sh"),
            Path("/home/click/.orca/agent-hooks/claude-hook.sh"),
        ):
            run(["/bin/sh", str(bridge)], {"hook_event_name": "Stop"}, env)

    if not args.quiet:
        print("PASS hook smoke: trio, nudge, context, export, UI, subagent, bridges")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
