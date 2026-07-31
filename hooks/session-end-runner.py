#!/usr/bin/env python3
"""Durable, serialized SessionEnd dispatcher.

The hook process only validates and queues the event, then starts a detached
drainer.  Drainers share one flock, so hooks that mutate $COMMAND_CENTER never race.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


MAX_EVENT_BYTES = 2_000_000
COMMAND_CENTER = Path(os.environ.get("COMMAND_CENTER") or (Path.home() / "main"))
STATE_ROOT = Path(
    os.environ.get("SESSION_END_STATE")
    or ((Path(os.environ["XDG_STATE_HOME"]) if os.environ.get("XDG_STATE_HOME") else Path.home() / ".local/state")
        / "claude-session-end")
)
QUEUE = STATE_ROOT / "queue"
FAILED = STATE_ROOT / "failed"
LOG = COMMAND_CENTER / "logs/hooks.log"
SAFE_ID = re.compile(r"[^A-Za-z0-9._-]+")


def hlog(message: str) -> None:
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as handle:
            handle.write(
                f"{datetime.now().isoformat(timespec='seconds')} [session-end-runner] {message}\n"
            )
    except OSError:
        pass


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temp = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    try:
        with temp.open("wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp, 0o600)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def read_hook_event() -> bytes:
    raw = sys.stdin.buffer.read(MAX_EVENT_BYTES + 1)
    if not raw or len(raw) > MAX_EVENT_BYTES:
        raise ValueError("missing or oversized SessionEnd event")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("SessionEnd event must be a JSON object")
    return (json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n").encode()


def enqueue(raw: bytes) -> Path:
    value = json.loads(raw)
    session_id = SAFE_ID.sub("-", str(value.get("session_id") or "nosid")).strip("-")[:48] or "nosid"
    digest = hashlib.sha256(raw).hexdigest()[:16]
    path = QUEUE / f"{session_id}-{digest}.json"
    atomic_write(path, raw)
    return path


def configured_steps() -> list[tuple[str, list[str], int, bool]]:
    python = sys.executable
    defaults = [
        (
            "summary",
            [python, str(Path.home() / ".claude/hooks/session-end-summary.py")],
            30,
            True,
        ),
        ("devlog", [python, str(COMMAND_CENTER / "system/devlog.py")], 30, True),
        (
            "sync",
            ["bash", str(COMMAND_CENTER / "system/dotclaude/sync.sh"), "--session-end"],
            240,
            False,
        ),
        (
            "techreport",
            [python, str(COMMAND_CENTER / "system/techreport-autopush.py")],
            120,
            False,
        ),
    ]
    steps = []
    for name, command, timeout, needs_event in defaults:
        override = os.environ.get(f"SESSION_END_STEP_{name.upper()}")
        if override:
            command = ["/bin/bash", "-lc", override]
        steps.append((name, command, timeout, needs_event))
    return steps


def run_event(path: Path) -> bool:
    processing = path.with_name(f".processing.{os.getpid()}.{path.name}")
    try:
        os.replace(path, processing)
    except FileNotFoundError:
        return True
    raw = processing.read_bytes()
    failures = []
    for name, command, timeout, needs_event in configured_steps():
        try:
            completed = subprocess.run(
                command,
                input=raw if needs_event else None,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                timeout=timeout,
                check=False,
            )
            if completed.returncode != 0:
                failures.append(f"{name}:exit={completed.returncode}")
                hlog(f"WARN {processing.name} {name} exit={completed.returncode}")
        except (OSError, subprocess.TimeoutExpired) as exc:
            failures.append(f"{name}:{type(exc).__name__}")
            hlog(f"WARN {processing.name} {name} failed={exc}")
    if failures:
        FAILED.mkdir(parents=True, exist_ok=True, mode=0o700)
        destination = FAILED / processing.name.replace(".processing.", "failed.", 1)
        os.replace(processing, destination)
        return False
    processing.unlink(missing_ok=True)
    return True


def drain() -> int:
    STATE_ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock_path = STATE_ROOT / "runner.lock"
    with lock_path.open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        processed = failed = 0
        while True:
            queued = sorted(QUEUE.glob("*.json")) if QUEUE.exists() else []
            if not queued:
                time.sleep(0.05)
                queued = sorted(QUEUE.glob("*.json")) if QUEUE.exists() else []
                if not queued:
                    break
            for path in queued:
                if run_event(path):
                    processed += 1
                else:
                    failed += 1
        if processed or failed:
            hlog(f"drain complete processed={processed} failed={failed}")
    return 0


def hook() -> int:
    try:
        queued = enqueue(read_hook_event())
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        hlog(f"invalid event: {exc}")
        return 0
    try:
        subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), "--drain"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
        )
    except OSError as exc:
        hlog(f"drainer spawn failed; event retained at {queued}: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(drain() if sys.argv[1:] == ["--drain"] else hook())
