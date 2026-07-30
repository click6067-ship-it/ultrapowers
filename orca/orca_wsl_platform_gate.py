#!/usr/bin/env python3
"""Fail-closed readiness gate for Orca running a repository in WSL2."""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Mapping, Sequence

CHECK_IDS = (
    "wsl2",
    "git_root",
    "repo_filesystem",
    "orca_status",
    "orca_worktree_identity",
    "linux_active_terminal",
)
COMMAND_TIMEOUT_SECONDS = 10
WINDOWS_MOUNT_RE = re.compile(r"^/mnt/[a-z](?:/|$)", re.IGNORECASE)
FORBIDDEN_FILESYSTEMS = {"9p", "drvfs"}


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str


@dataclass(frozen=True)
class Check:
    id: str
    ok: bool
    summary: str


@dataclass(frozen=True)
class WslUncPath:
    prefix: str
    distro: str
    posix_path: str


Runner = Callable[[Sequence[str], int], CommandResult]


def subprocess_runner(command: Sequence[str], timeout: int) -> CommandResult:
    completed = subprocess.run(
        list(command),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    return CommandResult(completed.returncode, completed.stdout)


def _run(command: Sequence[str], runner: Runner) -> tuple[CommandResult | None, str | None]:
    try:
        return runner(command, COMMAND_TIMEOUT_SECONDS), None
    except subprocess.TimeoutExpired:
        return None, "command timed out"
    except (OSError, ValueError):
        return None, "command could not be executed"


def _run_json(
    command: Sequence[str], runner: Runner
) -> tuple[dict[str, object] | None, str | None]:
    result, error = _run(command, runner)
    if error:
        return None, error
    assert result is not None
    if result.returncode != 0:
        return None, f"command exited {result.returncode}"
    try:
        payload = json.loads(result.stdout)
    except (json.JSONDecodeError, TypeError):
        return None, "command returned malformed JSON"
    if not isinstance(payload, dict):
        return None, "command returned an invalid JSON object"
    return payload, None


def _run_orca_json(
    command: Sequence[str], runner: Runner
) -> tuple[dict[str, object] | None, str | None]:
    payload, error = _run_json(command, runner)
    if error:
        return None, error
    assert payload is not None
    if payload.get("ok") is not True or not isinstance(payload.get("result"), dict):
        return None, "Orca response was not successful"
    return payload, None


def _resolve_orca_command(
    env: Mapping[str, str], platform_name: str
) -> tuple[str, ...]:
    configured = env.get("ORCA_CLI_COMMAND")
    if configured:
        command = tuple(shlex.split(configured))
        if not command:
            raise ValueError("ORCA_CLI_COMMAND is empty")
        return command
    if platform_name.startswith("linux"):
        return ("orca-ide",)
    raise ValueError("no default Orca CLI is defined for this platform")


def _normal_path(value: str) -> str:
    return os.path.normpath(value)


def parse_wsl_unc(value: object) -> WslUncPath | None:
    if not isinstance(value, str):
        return None
    if not value.startswith("\\\\") or "/" in value:
        return None
    parts = value[2:].split("\\")
    if len(parts) < 3:
        return None
    server, distro, *path_parts = parts
    if server.casefold() not in {"wsl.localhost", "wsl$"} or not distro:
        return None
    if any(not part or part in {".", ".."} for part in path_parts):
        return None
    return WslUncPath(
        prefix=value[: len(server) + 3],
        distro=distro,
        posix_path="/" + "/".join(path_parts),
    )


def unc_to_posix(value: object, expected_distro: str | None) -> str | None:
    parsed = parse_wsl_unc(value)
    if (
        parsed is None
        or not expected_distro
        or parsed.distro.casefold() != expected_distro.casefold()
    ):
        return None
    return _normal_path(parsed.posix_path)


def _terminal_worktree_unc(terminal: dict[str, object]) -> object:
    if "worktreePath" in terminal:
        return terminal["worktreePath"]
    pty_id = terminal.get("ptyId")
    if isinstance(pty_id, str):
        worktree_id = pty_id.split("@@", 1)[0]
        return worktree_id.split("::", 1)[-1]
    return None


def _terminal_is_linux_hosted(
    terminal: dict[str, object],
    repo_root: str,
    expected_distro: str | None,
    is_wsl2: bool,
) -> bool:
    mapped = unc_to_posix(_terminal_worktree_unc(terminal), expected_distro)
    if mapped != _normal_path(repo_root):
        return False
    if "hostPlatform" in terminal:
        host_platform = terminal["hostPlatform"]
        return (
            isinstance(host_platform, str)
            and host_platform.casefold() == "linux"
        )
    # Current Orca terminal-list JSON omits hostPlatform. In that schema the
    # exact caller's strict WSL UNC, current WSL2 kernel, and matching distro
    # together are the fail-closed Linux-host proof.
    return is_wsl2


def _safe_error(prefix: str, error: str | None) -> str:
    return f"{prefix}: {error or 'invalid response'}"


def run_gate(
    cwd: Path,
    env: Mapping[str, str] | None = None,
    runner: Runner = subprocess_runner,
    platform_name: str = sys.platform,
) -> list[Check]:
    env = os.environ if env is None else env
    checks: list[Check] = []
    expected_distro = env.get("WSL_DISTRO_NAME")
    caller_terminal_handle = env.get("ORCA_TERMINAL_HANDLE")

    uname, uname_error = _run(("uname", "-r"), runner)
    kernel = uname.stdout.strip() if uname and uname.returncode == 0 else ""
    is_wsl2 = (
        uname_error is None
        and uname is not None
        and uname.returncode == 0
        and "microsoft" in kernel.lower()
        and "wsl2" in kernel.lower()
    )
    checks.append(
        Check(
            "wsl2",
            is_wsl2,
            f"WSL2 kernel {kernel}" if is_wsl2 else "kernel is not identifiable as WSL2",
        )
    )

    git, git_error = _run(
        ("git", "-C", str(cwd), "rev-parse", "--show-toplevel"), runner
    )
    repo_root = git.stdout.strip() if git and git.returncode == 0 else ""
    git_ok = (
        git_error is None
        and git is not None
        and git.returncode == 0
        and os.path.isabs(repo_root)
    )
    checks.append(
        Check(
            "git_root",
            git_ok,
            f"Git root {repo_root}"
            if git_ok
            else "current directory has no absolute Git root",
        )
    )

    filesystem_ok = False
    filesystem_summary = "filesystem was not checked because Git root is unavailable"
    if git_ok:
        mount, mount_error = _run_json(
            (
                "findmnt",
                "-T",
                repo_root,
                "--json",
                "--output",
                "TARGET,SOURCE,FSTYPE",
            ),
            runner,
        )
        if mount_error:
            filesystem_summary = _safe_error("filesystem check failed", mount_error)
        else:
            assert mount is not None
            filesystems = mount.get("filesystems")
            filesystem_summary = "filesystem check returned an invalid mount"
            if (
                isinstance(filesystems, list)
                and filesystems
                and isinstance(filesystems[0], dict)
            ):
                filesystem = filesystems[0]
                fstype = filesystem.get("fstype")
                target = filesystem.get("target")
                normalized_fstype = (
                    fstype.lower() if isinstance(fstype, str) else ""
                )
                windows_path = bool(WINDOWS_MOUNT_RE.match(repo_root))
                filesystem_ok = (
                    normalized_fstype == "ext4"
                    and normalized_fstype not in FORBIDDEN_FILESYSTEMS
                    and not windows_path
                )
                filesystem_summary = (
                    f"repo is ext4 at {target}"
                    if filesystem_ok
                    else "repo must be ext4, not drvfs/9p or /mnt/<drive>"
                )
    checks.append(Check("repo_filesystem", filesystem_ok, filesystem_summary))

    try:
        orca = _resolve_orca_command(env, platform_name)
        orca_error = None
    except ValueError:
        orca = ()
        orca_error = "Orca CLI command is unavailable"

    status_payload = None
    if orca_error is None:
        status_payload, status_error = _run_orca_json(
            (*orca, "status", "--json"), runner
        )
    else:
        status_error = orca_error
    status_ok = False
    status_summary = _safe_error("Orca status failed", status_error)
    if status_payload is not None:
        result = status_payload["result"]
        assert isinstance(result, dict)
        app = result.get("app")
        runtime = result.get("runtime")
        if isinstance(app, dict) and isinstance(runtime, dict):
            state = runtime.get("state")
            reachable = runtime.get("reachable")
            status_ok = (
                app.get("running") is True
                and state == "ready"
                and reachable is True
            )
            status_summary = (
                "Orca runtime is ready and reachable"
                if status_ok
                else "Orca runtime is not running, ready, and reachable"
            )
    checks.append(Check("orca_status", status_ok, status_summary))

    worktree_payload = None
    if orca_error is None:
        worktree_payload, worktree_error = _run_orca_json(
            (*orca, "worktree", "current", "--json"), runner
        )
    else:
        worktree_error = orca_error
    identity_ok = False
    identity_summary = _safe_error("Orca worktree check failed", worktree_error)
    if worktree_payload is not None and git_ok:
        result = worktree_payload["result"]
        assert isinstance(result, dict)
        worktree = result.get("worktree")
        if isinstance(worktree, dict):
            mapped = unc_to_posix(worktree.get("path"), expected_distro)
            identity_ok = mapped == _normal_path(repo_root)
            identity_summary = (
                f"Orca worktree maps to {repo_root} in the current WSL distro"
                if identity_ok
                else "Orca worktree must be a strict same-distro WSL UNC for the Git root"
            )
    elif worktree_payload is not None:
        identity_summary = "Orca worktree cannot be compared without a Git root"
    checks.append(Check("orca_worktree_identity", identity_ok, identity_summary))

    terminal_payload = None
    if orca_error is None:
        terminal_payload, terminal_error = _run_orca_json(
            (*orca, "terminal", "list", "--worktree", "active", "--json"),
            runner,
        )
    else:
        terminal_error = orca_error
    terminal_ok = False
    terminal_summary = _safe_error("Orca terminal check failed", terminal_error)
    if terminal_payload is not None and git_ok:
        result = terminal_payload["result"]
        assert isinstance(result, dict)
        terminals = result.get("terminals")
        caller_matches = []
        if isinstance(terminals, list):
            caller_matches = [
                terminal
                for terminal in terminals
                if isinstance(terminal, dict)
                and caller_terminal_handle
                and terminal.get("handle") == caller_terminal_handle
            ]
        terminal_ok = (
            len(caller_matches) == 1
            and caller_matches[0].get("connected") is True
            and caller_matches[0].get("writable") is True
            and caller_matches[0].get("orphaned") is False
            and _terminal_is_linux_hosted(
                caller_matches[0],
                repo_root,
                expected_distro,
                is_wsl2,
            )
        )
        terminal_summary = (
            "exact caller terminal is connected, writable, and Linux-hosted"
            if terminal_ok
            else "exact caller terminal is not a same-worktree connected writable Linux terminal"
        )
    elif terminal_payload is not None:
        terminal_summary = "Orca terminals cannot be compared without a Git root"
    checks.append(Check("linux_active_terminal", terminal_ok, terminal_summary))

    assert tuple(check.id for check in checks) == CHECK_IDS
    return checks


def render_human(checks: Sequence[Check]) -> str:
    ok = all(check.ok for check in checks)
    lines = [f"{'PASS' if ok else 'FAIL'} Orca-WSL platform gate"]
    lines.extend(
        f"[{'PASS' if check.ok else 'FAIL'}] {check.id}: {check.summary}"
        for check in checks
    )
    return "\n".join(lines)


def render_json(checks: Sequence[Check]) -> str:
    return json.dumps(
        {
            "version": 1,
            "ok": all(check.ok for check in checks),
            "checks": [asdict(check) for check in checks],
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit stable JSON output")
    args = parser.parse_args(argv)
    checks = run_gate(Path.cwd())
    print(render_json(checks) if args.json else render_human(checks))
    return 0 if all(check.ok for check in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
