#!/usr/bin/env python3
"""Regression tests for orca-wsl-bridge.ps1 native argument quoting.

2026-07-30: Windows PowerShell 5.1 rebuilt the `& exe @args` native command
line without escaping embedded double quotes, so orchestration specs, --deps
arrays, and JSON payloads reached orca.exe with their quotes consumed. The
bridge now assembles the command line itself (inverse CommandLineToArgvW
rules). These tests round-trip adversarial argv vectors through the repo
bridge's -SelfTestArgEscaping mode, which parses the escaped line back with
the real Win32 CommandLineToArgvW. Only the repo script is exercised — the
live bridge under ~/.local/share/orca is never invoked and no orca.exe child
is launched.
"""

from __future__ import annotations

import base64
import json
import shutil
import subprocess
import unittest
from pathlib import Path

BRIDGE = Path(__file__).with_name("orca-wsl-bridge.ps1")
FALLBACK_POWERSHELL = Path(
    "/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"
)

# The three coordinator-measured 2026-07-30 regressions plus the escaping
# edge families: quotes, backslash-quote runs, trailing backslashes, empty
# arguments, whitespace, and combinations.
VECTORS = [
    "plain",
    "--json",
    "has space",
    "two  spaces",
    'X "double" [brackets]',  # task-create --spec repro (task_6acc4eee84b6)
    '["task_6e3cd8a28ad2"]',  # --deps repro (Invalid --deps rejection)
    '{"probeKey":"probeValue","n":1}',  # send --payload repro (msg_a44828f1985d)
    "",
    '"',
    '""',
    'embedded"quote',
    'backslash-quote\\"',
    'a\\\\"b',
    "trailing\\",
    "trailing\\\\",
    "C:\\Users\\click\\path with space\\",
    "tab\there",
    'combo \\" \\\\" mix\\',
    '한글 "따옴표" 조합',
]


def find_powershell() -> str | None:
    found = shutil.which("powershell.exe")
    if found:
        return found
    if FALLBACK_POWERSHELL.is_file():
        return str(FALLBACK_POWERSHELL)
    return None


def bridge_selftest_argv(vectors: list[str]) -> list[str]:
    powershell = find_powershell()
    assert powershell is not None
    windows_bridge = subprocess.run(
        ["wslpath", "-w", str(BRIDGE)],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    ).stdout.strip()
    encoded = base64.b64encode(
        json.dumps(vectors, ensure_ascii=False).encode("utf-8")
    ).decode("ascii")
    completed = subprocess.run(
        [
            powershell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            windows_bridge,
            "-SelfTestArgEscaping",
            "-ForwardArgsB64",
            encoded,
        ],
        capture_output=True,
        text=True,
        timeout=180,
    )
    if completed.returncode != 0:
        raise AssertionError(
            f"self-test exited {completed.returncode}: {completed.stderr.strip()}"
        )
    payload = json.loads(base64.b64decode(completed.stdout.strip()))
    argv = payload["argv"]
    assert isinstance(argv, list)
    return argv


class BridgeSourceShapeTest(unittest.TestCase):
    """Hermetic pins on the repaired invocation leg (no interop needed)."""

    def setUp(self) -> None:
        self.source = BRIDGE.read_text(encoding="utf-8")

    def test_naive_splat_invocation_is_gone(self) -> None:
        # The quote-losing PS 5.1 leg must never come back.
        self.assertNotIn("& $OrcaLauncher @ForwardArgs", self.source)

    def test_repaired_leg_components_are_present(self) -> None:
        for needle in (
            "function ConvertTo-NativeArgument",
            "function ConvertTo-NativeCommandLine",
            "CommandLineToArgvW",
            "System.Diagnostics.ProcessStartInfo",
            "$startInfo.UseShellExecute = $false",
            "Repair-CaseFoldedProcessPath",
            "ORCA_CLI_CWD",
            "Push-Location",
        ):
            self.assertIn(needle, self.source)

    def test_selftest_leg_never_references_the_launcher(self) -> None:
        selftest = self.source.split("if ($PSCmdlet.ParameterSetName", 1)[1]
        selftest = selftest.split("$exitCode = 0\ntry {", 1)[0]
        self.assertNotIn("$OrcaLauncher", selftest)
        self.assertNotIn("Process]::Start", selftest)


@unittest.skipIf(
    find_powershell() is None, "powershell.exe interop is unavailable"
)
class BridgeEscapingRoundTripTest(unittest.TestCase):
    """Real powershell.exe 5.1 round-trip against Win32 CommandLineToArgvW."""

    def test_adversarial_vectors_round_trip_exactly(self) -> None:
        self.assertEqual(bridge_selftest_argv(VECTORS), VECTORS)

    def test_each_vector_round_trips_alone(self) -> None:
        # Single-argument runs catch escaping bugs that joining could mask
        # (e.g. a trailing backslash eating the separator space).
        for vector in VECTORS:
            with self.subTest(vector=vector):
                self.assertEqual(bridge_selftest_argv([vector]), [vector])

    def test_empty_argv_round_trips(self) -> None:
        self.assertEqual(bridge_selftest_argv([]), [])


if __name__ == "__main__":
    unittest.main()
