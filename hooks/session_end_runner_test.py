#!/usr/bin/env python3
"""Concurrency and failure tests for session-end-runner.py."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT = Path(__file__).with_name("session-end-runner.py")
SPEC = importlib.util.spec_from_file_location("session_end_runner", SCRIPT)
assert SPEC and SPEC.loader
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)


class RunnerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.queue = self.root / "queue"
        self.failed = self.root / "failed"
        self.log = self.root / "hooks.log"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def event(self, index: int) -> bytes:
        return (
            json.dumps(
                {
                    "session_id": f"session-{index}",
                    "transcript_path": f"/tmp/transcript-{index}.jsonl",
                    "cwd": "/tmp",
                    "reason": "exit",
                }
            )
            + "\n"
        ).encode()

    def test_ten_events_are_drained_exactly_once(self):
        calls = []

        def fake_run(command, **kwargs):
            calls.append((tuple(command), kwargs.get("input")))
            return subprocess.CompletedProcess(command, 0)

        with (
            patch.object(RUNNER, "STATE_ROOT", self.root),
            patch.object(RUNNER, "QUEUE", self.queue),
            patch.object(RUNNER, "FAILED", self.failed),
            patch.object(RUNNER, "LOG", self.log),
            patch.object(RUNNER, "configured_steps", return_value=[("one", ["true"], 5, True)]),
            patch.object(RUNNER.subprocess, "run", side_effect=fake_run),
        ):
            for index in range(10):
                RUNNER.enqueue(self.event(index))
            self.assertEqual(RUNNER.drain(), 0)
        self.assertEqual(len(calls), 10)
        self.assertFalse(list(self.queue.glob("*.json")))
        session_ids = {json.loads(raw)["session_id"] for _, raw in calls}
        self.assertEqual(len(session_ids), 10)

    def test_failed_step_is_quarantined(self):
        with (
            patch.object(RUNNER, "STATE_ROOT", self.root),
            patch.object(RUNNER, "QUEUE", self.queue),
            patch.object(RUNNER, "FAILED", self.failed),
            patch.object(RUNNER, "LOG", self.log),
            patch.object(RUNNER, "configured_steps", return_value=[("bad", ["false"], 5, False)]),
            patch.object(
                RUNNER.subprocess,
                "run",
                return_value=subprocess.CompletedProcess(["false"], 7),
            ),
        ):
            RUNNER.enqueue(self.event(1))
            RUNNER.drain()
        self.assertEqual(len(list(self.failed.iterdir())), 1)


if __name__ == "__main__":
    unittest.main()
