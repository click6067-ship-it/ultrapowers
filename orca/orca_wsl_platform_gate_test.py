#!/usr/bin/env python3
"""Deterministic tests for orca_wsl_platform_gate.py."""

from __future__ import annotations

import json
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Sequence
from unittest import mock

import orca_wsl_platform_gate as gate


def command_result(payload: object, returncode: int = 0) -> gate.CommandResult:
    stdout = payload if isinstance(payload, str) else json.dumps(payload)
    return gate.CommandResult(returncode, stdout)


def orca_result(result: dict[str, object]) -> gate.CommandResult:
    return command_result({"ok": True, "result": result})


def unc_for(
    path: str, *, distro: str = "Ubuntu", server: str = "wsl.localhost"
) -> str:
    return f"\\\\{server}\\{distro}" + path.replace("/", "\\")


def terminal_payload(
    repo: str,
    *,
    connected: bool = True,
    writable: bool = True,
    active: bool = True,
    orphaned: bool = False,
    host_platform: str | None = None,
    worktree_path: str | None = None,
) -> dict[str, object]:
    terminal: dict[str, object] = {
        "handle": "term-linux",
        "connected": connected,
        "writable": writable,
        "orphaned": orphaned,
        "worktreePath": worktree_path or unc_for(repo),
    }
    if host_platform is not None:
        terminal["hostPlatform"] = host_platform
    return {
        "terminals": [terminal],
        "visualLayouts": [
            {
                "root": {
                    "type": "group",
                    "activeTabId": "tab-linux",
                    "tabs": [
                        {
                            "tabId": "tab-linux",
                            "panes": {
                                "type": "terminal",
                                "handle": "term-linux",
                                "active": active,
                            },
                        }
                    ],
                }
            }
        ],
    }


def success_responses(
    repo: str = "/home/click/project",
    orca: tuple[str, ...] = ("orca-ide",),
) -> dict[tuple[str, ...], gate.CommandResult]:
    cwd = Path(repo)
    return {
        ("uname", "-r"): command_result(
            "6.18.33.2-microsoft-standard-WSL2\n"
        ),
        ("git", "-C", str(cwd), "rev-parse", "--show-toplevel"): command_result(
            repo + "\n"
        ),
        (
            "findmnt",
            "-T",
            repo,
            "--json",
            "--output",
            "TARGET,SOURCE,FSTYPE",
        ): command_result(
            {
                "filesystems": [
                    {"target": "/", "source": "/dev/sdd", "fstype": "ext4"}
                ]
            }
        ),
        (*orca, "status", "--json"): orca_result(
            {
                "app": {"running": True},
                "runtime": {"state": "ready", "reachable": True},
            }
        ),
        (*orca, "worktree", "current", "--json"): orca_result(
            {"worktree": {"path": unc_for(repo)}}
        ),
        (
            *orca,
            "terminal",
            "list",
            "--worktree",
            "active",
            "--json",
        ): orca_result(terminal_payload(repo)),
    }


class FakeRunner:
    def __init__(
        self,
        responses: dict[
            tuple[str, ...], gate.CommandResult | BaseException
        ],
    ) -> None:
        self.responses = responses
        self.calls: list[tuple[tuple[str, ...], int]] = []

    def __call__(
        self, command: Sequence[str], timeout: int
    ) -> gate.CommandResult:
        key = tuple(command)
        self.calls.append((key, timeout))
        response = self.responses[key]
        if isinstance(response, BaseException):
            raise response
        return response


class PlatformGateTest(unittest.TestCase):
    repo = "/home/click/project"
    success_env = {
        "WSL_DISTRO_NAME": "Ubuntu",
        "ORCA_TERMINAL_HANDLE": "term-linux",
    }

    def run_checks(
        self,
        responses: dict[tuple[str, ...], gate.CommandResult | BaseException],
        *,
        env: dict[str, str] | None = None,
    ) -> tuple[dict[str, gate.Check], FakeRunner]:
        runner = FakeRunner(responses)
        checks = gate.run_gate(
            Path(self.repo),
            env=self.success_env if env is None else env,
            runner=runner,
            platform_name="linux",
        )
        return {check.id: check for check in checks}, runner

    def test_success_has_stable_ids_and_timeouts(self) -> None:
        checks, runner = self.run_checks(success_responses(self.repo))

        self.assertEqual(tuple(checks), gate.CHECK_IDS)
        self.assertTrue(all(check.ok for check in checks.values()))
        self.assertTrue(runner.calls)
        self.assertTrue(
            all(timeout == gate.COMMAND_TIMEOUT_SECONDS for _, timeout in runner.calls)
        )
        rendered = json.loads(gate.render_json(list(checks.values())))
        self.assertEqual(rendered["version"], 1)
        self.assertTrue(rendered["ok"])
        self.assertEqual(
            [item["id"] for item in rendered["checks"]], list(gate.CHECK_IDS)
        )

    def test_distro_match_is_case_insensitive(self) -> None:
        checks, _ = self.run_checks(
            success_responses(self.repo),
            env={
                "WSL_DISTRO_NAME": "ubuntu",
                "ORCA_TERMINAL_HANDLE": "term-linux",
            },
        )

        self.assertTrue(checks["orca_worktree_identity"].ok)
        self.assertTrue(checks["linux_active_terminal"].ok)

    def test_wsl_unc_parser_preserves_prefix_distro_and_path(self) -> None:
        value = unc_for(
            self.repo,
            distro="uBuntu",
            server="WSL.Localhost",
        )

        parsed = gate.parse_wsl_unc(value)

        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.prefix, "\\\\WSL.Localhost\\")
        self.assertEqual(parsed.distro, "uBuntu")
        self.assertEqual(parsed.posix_path, self.repo)

    def test_non_wsl_kernel_fails(self) -> None:
        responses = success_responses(self.repo)
        responses[("uname", "-r")] = command_result("6.8.0-generic\n")

        checks, _ = self.run_checks(responses)

        self.assertFalse(checks["wsl2"].ok)
        self.assertFalse(checks["linux_active_terminal"].ok)

    def test_missing_distro_fails_worktree_and_caller_terminal(self) -> None:
        checks, _ = self.run_checks(
            success_responses(self.repo),
            env={"ORCA_TERMINAL_HANDLE": "term-linux"},
        )

        self.assertFalse(checks["orca_worktree_identity"].ok)
        self.assertFalse(checks["linux_active_terminal"].ok)

    def test_missing_git_root_fails_closed(self) -> None:
        responses = success_responses(self.repo)
        responses[
            ("git", "-C", self.repo, "rev-parse", "--show-toplevel")
        ] = command_result("", returncode=128)
        del responses[
            (
                "findmnt",
                "-T",
                self.repo,
                "--json",
                "--output",
                "TARGET,SOURCE,FSTYPE",
            )
        ]

        checks, _ = self.run_checks(responses)

        self.assertFalse(checks["git_root"].ok)
        self.assertFalse(checks["repo_filesystem"].ok)
        self.assertFalse(checks["orca_worktree_identity"].ok)

    def test_drvfs_and_9p_filesystems_fail(self) -> None:
        findmnt_command = (
            "findmnt",
            "-T",
            self.repo,
            "--json",
            "--output",
            "TARGET,SOURCE,FSTYPE",
        )
        for fstype in ("drvfs", "9p"):
            with self.subTest(fstype=fstype):
                responses = success_responses(self.repo)
                responses[findmnt_command] = command_result(
                    {
                        "filesystems": [
                            {
                                "target": "/mnt/c",
                                "source": "C:",
                                "fstype": fstype,
                            }
                        ]
                    }
                )
                checks, _ = self.run_checks(responses)
                self.assertFalse(checks["repo_filesystem"].ok)

    def test_windows_mounted_repo_fails_even_if_mount_claims_ext4(self) -> None:
        windows_repo = "/mnt/c/project"
        responses = success_responses(windows_repo)
        runner = FakeRunner(responses)

        checks = gate.run_gate(
            Path(windows_repo),
            env={},
            runner=runner,
            platform_name="linux",
        )
        by_id = {check.id: check for check in checks}

        self.assertTrue(by_id["git_root"].ok)
        self.assertFalse(by_id["repo_filesystem"].ok)

    def test_unready_orca_runtime_fails(self) -> None:
        responses = success_responses(self.repo)
        responses[("orca-ide", "status", "--json")] = orca_result(
            {
                "app": {"running": True},
                "runtime": {"state": "starting", "reachable": True},
            }
        )

        checks, _ = self.run_checks(responses)

        self.assertFalse(checks["orca_status"].ok)

    def test_cross_distro_unc_fails_worktree_and_caller_terminal(self) -> None:
        responses = success_responses(self.repo)
        responses[
            ("orca-ide", "worktree", "current", "--json")
        ] = orca_result(
            {"worktree": {"path": unc_for(self.repo, distro="Debian")}}
        )
        responses[
            (
                "orca-ide",
                "terminal",
                "list",
                "--worktree",
                "active",
                "--json",
            )
        ] = orca_result(
            terminal_payload(
                self.repo,
                worktree_path=unc_for(self.repo, distro="Debian"),
            )
        )

        checks, _ = self.run_checks(responses)

        self.assertFalse(checks["orca_worktree_identity"].ok)
        self.assertFalse(checks["linux_active_terminal"].ok)

    def test_malformed_and_non_unc_paths_fail_closed(self) -> None:
        paths = {
            "single-leading-backslash": (
                "\\wsl.localhost\\Ubuntu" + self.repo.replace("/", "\\")
            ),
            "forward-slash-path": "//wsl.localhost/Ubuntu" + self.repo,
            "malformed-server": (
                "\\\\wsl.invalid\\Ubuntu" + self.repo.replace("/", "\\")
            ),
        }
        for name, path in paths.items():
            with self.subTest(name=name):
                responses = success_responses(self.repo)
                responses[
                    ("orca-ide", "worktree", "current", "--json")
                ] = orca_result({"worktree": {"path": path}})
                responses[
                    (
                        "orca-ide",
                        "terminal",
                        "list",
                        "--worktree",
                        "active",
                        "--json",
                    )
                ] = orca_result(
                    terminal_payload(self.repo, worktree_path=path)
                )

                checks, _ = self.run_checks(responses)

                self.assertFalse(checks["orca_worktree_identity"].ok)
                self.assertFalse(checks["linux_active_terminal"].ok)

    def test_caller_terminal_must_be_connected_writable_and_not_orphaned(
        self,
    ) -> None:
        terminal_command = (
            "orca-ide",
            "terminal",
            "list",
            "--worktree",
            "active",
            "--json",
        )
        cases = {
            "disconnected": terminal_payload(self.repo, connected=False),
            "read-only": terminal_payload(self.repo, writable=False),
            "orphaned": terminal_payload(self.repo, orphaned=True),
        }
        for name, payload in cases.items():
            with self.subTest(name=name):
                responses = success_responses(self.repo)
                responses[terminal_command] = orca_result(payload)
                checks, _ = self.run_checks(responses)
                self.assertFalse(checks["linux_active_terminal"].ok)

    def test_unrelated_ui_selection_cannot_authorize_bad_caller(self) -> None:
        responses = success_responses(self.repo)
        payload = terminal_payload(self.repo, connected=False, active=False)
        payload["terminals"].append(
            {
                "handle": "term-ui-selected",
                "connected": True,
                "writable": True,
                "orphaned": False,
                "hostPlatform": "linux",
                "worktreePath": unc_for(self.repo),
            }
        )
        root = payload["visualLayouts"][0]["root"]
        root["activeTabId"] = "tab-ui-selected"
        root["tabs"].append(
            {
                "tabId": "tab-ui-selected",
                "panes": {
                    "type": "terminal",
                    "handle": "term-ui-selected",
                    "active": True,
                },
            }
        )
        responses[
            (
                "orca-ide",
                "terminal",
                "list",
                "--worktree",
                "active",
                "--json",
            )
        ] = orca_result(payload)

        checks, _ = self.run_checks(responses)

        self.assertFalse(checks["linux_active_terminal"].ok)

    def test_missing_caller_handle_fails(self) -> None:
        cases = {
            "environment-variable-absent": {
                "WSL_DISTRO_NAME": "Ubuntu",
            },
            "handle-not-in-list": {
                "WSL_DISTRO_NAME": "Ubuntu",
                "ORCA_TERMINAL_HANDLE": "term-missing",
            },
        }
        for name, env in cases.items():
            with self.subTest(name=name):
                checks, _ = self.run_checks(
                    success_responses(self.repo),
                    env=env,
                )
                self.assertFalse(checks["linux_active_terminal"].ok)

    def test_windows_caller_host_fails(self) -> None:
        responses = success_responses(self.repo)
        responses[
            (
                "orca-ide",
                "terminal",
                "list",
                "--worktree",
                "active",
                "--json",
            )
        ] = orca_result(
            terminal_payload(self.repo, host_platform="win32")
        )

        checks, _ = self.run_checks(responses)

        self.assertFalse(checks["linux_active_terminal"].ok)

    def test_other_worktree_caller_fails(self) -> None:
        responses = success_responses(self.repo)
        responses[
            (
                "orca-ide",
                "terminal",
                "list",
                "--worktree",
                "active",
                "--json",
            )
        ] = orca_result(
            terminal_payload(
                self.repo,
                host_platform="linux",
                worktree_path=unc_for("/home/click/other-project"),
            )
        )

        checks, _ = self.run_checks(responses)

        self.assertFalse(checks["linux_active_terminal"].ok)

    def test_malformed_json_fails_without_echoing_raw_output(self) -> None:
        responses = success_responses(self.repo)
        responses[("orca-ide", "status", "--json")] = command_result(
            "secret-marker: not JSON"
        )

        checks, _ = self.run_checks(responses)

        self.assertFalse(checks["orca_status"].ok)
        self.assertNotIn("secret-marker", checks["orca_status"].summary)

    def test_timeout_fails_without_command_output(self) -> None:
        responses = success_responses(self.repo)
        responses[("uname", "-r")] = subprocess.TimeoutExpired(
            ("uname", "-r"), gate.COMMAND_TIMEOUT_SECONDS
        )

        checks, _ = self.run_checks(responses)

        self.assertFalse(checks["wsl2"].ok)

    def test_real_subprocess_timeout_is_enforced(self) -> None:
        command = (
            sys.executable,
            "-c",
            "import time; time.sleep(2)",
        )
        with mock.patch.object(gate, "COMMAND_TIMEOUT_SECONDS", 0.05):
            result, error = gate._run(command, gate.subprocess_runner)

        self.assertIsNone(result)
        self.assertEqual(error, "command timed out")

    def test_orca_cli_command_override_is_used_without_shell(self) -> None:
        custom = ("custom-orca", "--profile", "local")
        responses = success_responses(self.repo, orca=custom)

        checks, runner = self.run_checks(
            responses,
            env={
                **self.success_env,
                "ORCA_CLI_COMMAND": "custom-orca --profile local",
            },
        )

        self.assertTrue(all(check.ok for check in checks.values()))
        self.assertIn((*custom, "status", "--json"), [call for call, _ in runner.calls])

    def test_orca_cli_metacharacters_are_argv_not_shell_syntax(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            sentinel = Path(temp_dir) / "shell-executed"
            configured = (
                f"{shlex.quote(sys.executable)} -c pass ; "
                f"touch {shlex.quote(str(sentinel))}"
            )

            command = gate._resolve_orca_command(
                {"ORCA_CLI_COMMAND": configured},
                "linux",
            )
            result, error = gate._run(command, gate.subprocess_runner)

            self.assertIsNone(error)
            self.assertIsNotNone(result)
            assert result is not None
            self.assertEqual(result.returncode, 0)
            self.assertIn(";", command)
            self.assertFalse(sentinel.exists())


if __name__ == "__main__":
    unittest.main()
