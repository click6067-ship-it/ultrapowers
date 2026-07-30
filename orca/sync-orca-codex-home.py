#!/usr/bin/env python3
"""Keep Orca's redirected CODEX_HOME aligned with the personal Codex policy.

Orca owns its runtime config, hooks, and WSL launcher, so this script preserves
them while enforcing four personal invariants:

1. runtime AGENTS.md is byte-identical to ~/.codex/AGENTS.md;
2. the canonical Bash guardrail exists alongside Orca's bridge hook;
3. only that exact normalized hook definition is marked trusted.
4. regenerated WSL launcher files match the reviewed PATH/argv bridge.

The trust hash follows Codex's public command-hook normalization algorithm.
"""

from __future__ import annotations

import argparse
import base64
import fcntl
import hashlib
import json
import os
import re
import tempfile
import tomllib
from pathlib import Path


HOME = Path.home()
CANONICAL_HOME = HOME / ".codex"
RUNTIME_HOME = HOME / ".local/share/orca/codex-runtime-home/home"
WSL_BRIDGE_SOURCE = Path(__file__).with_name("orca-wsl-bridge.ps1")
WSL_WRAPPER_SOURCE = Path(__file__).with_name("orca-ide-wsl-wrapper.sh")
WSL_BRIDGE_TARGET = HOME / ".local/share/orca/orca-wsl-bridge.ps1"
WSL_WRAPPER_TARGET = HOME / ".local/bin/orca-ide"
LAUNCHER_B64_TOKEN = "__ORCA_WIN_LAUNCHER_B64__"
POLICY_COMMAND = "python3 /home/click/main/system/guardrail.py"
STATE_MARKER = "# managed-by: sync-orca-codex-home"
EVENT_LABELS = {
    "PreToolUse": "pre_tool_use",
    "PermissionRequest": "permission_request",
    "PostToolUse": "post_tool_use",
    "PreCompact": "pre_compact",
    "PostCompact": "post_compact",
    "SessionStart": "session_start",
    "SessionEnd": "session_end",
    "UserPromptSubmit": "user_prompt_submit",
    "SubagentStart": "subagent_start",
    "SubagentStop": "subagent_stop",
    "Stop": "stop",
}
ORCA_BRIDGE_EVENTS = {
    "PreToolUse",
    "PermissionRequest",
    "PostToolUse",
    "SessionStart",
    "UserPromptSubmit",
    "SubagentStart",
    "SubagentStop",
    "Stop",
}


def atomic_write(path: Path, data: bytes, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw_tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    tmp = Path(raw_tmp)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if mode is None and path.exists():
            mode = path.stat().st_mode & 0o777
        os.chmod(tmp, mode or 0o600)
        os.replace(tmp, path)
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass


def policy_group() -> dict:
    source = json.loads((CANONICAL_HOME / "hooks.json").read_text(encoding="utf-8"))
    groups = source.get("hooks", {}).get("PreToolUse", [])
    matches = [
        group
        for group in groups
        if any(
            handler.get("type") == "command"
            and handler.get("command") == POLICY_COMMAND
            for handler in group.get("hooks", [])
        )
    ]
    if len(matches) != 1:
        raise RuntimeError("canonical hooks.json must contain exactly one Bash guardrail")
    return matches[0]


def normalized_hook_hash(event_name: str, group: dict) -> str:
    if event_name not in EVENT_LABELS:
        raise RuntimeError(f"unsupported hook event: {event_name}")
    if len(group.get("hooks", [])) != 1:
        raise RuntimeError("trusted hook groups must contain exactly one handler")
    matcher = group.get("matcher")
    handler = group["hooks"][0]
    timeout = max(int(handler.get("timeout", 600)), 1)
    if event_name == "SessionEnd":
        timeout = min(timeout, 3)
    normalized = {
        "event_name": EVENT_LABELS[event_name],
        "hooks": [
            {
                "async": bool(handler.get("async", False)),
                "command": handler["command"],
                "timeout": timeout,
                "type": "command",
            }
        ],
    }
    if matcher is not None and event_name not in {"UserPromptSubmit", "Stop"}:
        normalized["matcher"] = matcher
    if handler.get("statusMessage") is not None:
        normalized["hooks"][0]["statusMessage"] = handler["statusMessage"]
    if (
        event_name
        in {
            "PreToolUse",
            "PostToolUse",
            "SessionStart",
            "UserPromptSubmit",
            "SubagentStart",
        }
        and handler.get("additionalContextLimit") not in (None, 2500)
    ):
        normalized["hooks"][0]["additionalContextLimit"] = handler["additionalContextLimit"]
    serialized = json.dumps(
        normalized, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(serialized).hexdigest()


def sync_agents(check: bool) -> tuple[bool, str]:
    source = CANONICAL_HOME / "AGENTS.md"
    target = RUNTIME_HOME / "AGENTS.md"
    expected = source.read_bytes()
    changed = not target.exists() or target.read_bytes() != expected
    if changed and not check:
        atomic_write(target, expected, mode=0o644)
    return changed, "AGENTS.md"


def sync_runtime_hooks(group: dict, check: bool) -> tuple[bool, str, int, dict]:
    """Ensure exactly one canonical guardrail group, at any position.

    Orca's codex-accounts regeneration rebuilds this file as
    [canonical user hooks..., orca bridge] while this script used to force the
    guardrail last; the two writers flipped the order forever (2026-07-30
    root-cause report). Position is not load-bearing — every PreToolUse group
    runs — so only content is enforced: exactly one byte-identical guardrail,
    kept where the current file has it, appended only when missing.
    """
    path = RUNTIME_HOME / "hooks.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    hooks = data.setdefault("hooks", {})
    groups = hooks.setdefault("PreToolUse", [])

    def is_guard(item: dict) -> bool:
        return any(
            handler.get("type") == "command"
            and handler.get("command") == POLICY_COMMAND
            for handler in item.get("hooks", [])
        )

    guard_positions = [i for i, item in enumerate(groups) if is_guard(item)]
    if guard_positions:
        first = guard_positions[0]
        expected_groups = [
            group if index == first else item
            for index, item in enumerate(groups)
            if index == first or not is_guard(item)
        ]
        guard_index = first
    else:
        expected_groups = list(groups) + [group]
        guard_index = len(groups)
    changed = groups != expected_groups
    if changed and not check:
        hooks["PreToolUse"] = expected_groups
        payload = (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        atomic_write(path, payload, mode=0o600)
    return changed, "runtime hooks.json", guard_index, hooks


def orca_bridge_commands(path: Path) -> set[str]:
    quoted = f"'{path}'"
    commands = set()
    for executable_check in ("", f" && [ -x {quoted} ]"):
        prefix = f"if [ -f {quoted} ] && [ -r {quoted} ]{executable_check}; "
        commands.add(
            prefix + f"then /bin/sh {quoted}; else cat >/dev/null 2>&1 || :; fi"
        )
        commands.add(
            prefix
            + f"then /bin/sh {quoted}; "
            + "else { command -p cat 2>/dev/null || cat; } >/dev/null 2>&1 || :; fi"
        )
    return commands


def expected_orca_bridge(command: str) -> bool:
    allowed_paths = [
        HOME / ".orca/agent-hooks/codex-hook.sh",
        RUNTIME_HOME / ".orca/agent-hooks/codex-hook.sh",
    ]
    return any(command in orca_bridge_commands(path) for path in allowed_paths)


def launcher_b64_from_wrapper(text: str) -> str:
    matches = re.findall(r"(?m)^# ORCA_WIN_LAUNCHER_B64=([A-Za-z0-9+/=]+)$", text)
    if len(matches) != 1:
        raise RuntimeError("Orca WSL wrapper must contain exactly one launcher marker")
    encoded = matches[0]
    try:
        launcher = base64.b64decode(encoded, validate=True).decode("utf-8")
    except (ValueError, UnicodeDecodeError) as exc:
        raise RuntimeError("Orca WSL wrapper launcher marker is invalid") from exc
    if not re.fullmatch(r"[A-Za-z]:\\[^'\r\n]+\\orca\.exe", launcher, re.IGNORECASE):
        raise RuntimeError("Orca WSL wrapper launcher path is not an Orca executable")
    return encoded


def render_wsl_wrapper(current: str, template: str) -> bytes:
    encoded = launcher_b64_from_wrapper(current)
    if template.count(LAUNCHER_B64_TOKEN) != 2:
        raise RuntimeError("Orca WSL wrapper template launcher token count changed")
    return template.replace(LAUNCHER_B64_TOKEN, encoded).encode("utf-8")


def sync_wsl_launcher(check: bool) -> list[tuple[bool, str]]:
    """Restore the WSL wrapper/bridge that Orca may regenerate at terminal lifecycle."""
    if not WSL_WRAPPER_TARGET.is_file() or not WSL_BRIDGE_TARGET.is_file():
        try:
            is_wsl = "microsoft" in Path("/proc/sys/kernel/osrelease").read_text().lower()
        except OSError:
            is_wsl = False
        if is_wsl:
            missing = [
                str(path)
                for path in (WSL_WRAPPER_TARGET, WSL_BRIDGE_TARGET)
                if not path.is_file()
            ]
            raise RuntimeError("missing Orca WSL launcher files: " + ", ".join(missing))
        return []
    bridge_expected = WSL_BRIDGE_SOURCE.read_bytes()
    current_wrapper = WSL_WRAPPER_TARGET.read_text(encoding="utf-8")
    wrapper_expected = render_wsl_wrapper(
        current_wrapper, WSL_WRAPPER_SOURCE.read_text(encoding="utf-8")
    )
    results = [
        (WSL_BRIDGE_TARGET.read_bytes() != bridge_expected, "Orca WSL bridge"),
        (WSL_WRAPPER_TARGET.read_bytes() != wrapper_expected, "Orca WSL wrapper"),
    ]
    if not check:
        if results[0][0]:
            atomic_write(WSL_BRIDGE_TARGET, bridge_expected, mode=0o644)
        if results[1][0]:
            atomic_write(WSL_WRAPPER_TARGET, wrapper_expected, mode=0o755)
    return results


def runtime_trust_entries(hooks: dict) -> list[tuple[str, int, int, str]]:
    entries = []
    guard_count = 0
    for event_name, groups in hooks.items():
        if event_name not in EVENT_LABELS:
            raise RuntimeError(f"unrecognized runtime hook event: {event_name}")
        for group_index, group in enumerate(groups):
            handlers = group.get("hooks", [])
            if len(handlers) != 1:
                raise RuntimeError(
                    f"{event_name}:{group_index} must contain exactly one handler"
                )
            handler = handlers[0]
            command = handler.get("command", "")
            if command == POLICY_COMMAND:
                if (
                    event_name != "PreToolUse"
                    or handler.get("type") != "command"
                    or group.get("matcher") != "^Bash$"
                ):
                    raise RuntimeError("guardrail hook shape changed")
                guard_count += 1
            else:
                allowed_keys = {"type", "command", "timeout"}
                if (
                    event_name not in ORCA_BRIDGE_EVENTS
                    or group.get("matcher") is not None
                    or handler.get("type") != "command"
                    or handler.get("timeout") != 10
                    or set(handler) - allowed_keys
                    or not expected_orca_bridge(command)
                ):
                    raise RuntimeError(
                        f"refusing to trust unrecognized Orca hook "
                        f"{event_name}:{group_index}:0"
                    )
            entries.append(
                (
                    EVENT_LABELS[event_name],
                    group_index,
                    0,
                    normalized_hook_hash(event_name, group),
                )
            )
    if guard_count != 1:
        raise RuntimeError("runtime hooks must contain exactly one guardrail")
    return entries


def toml_escape_key(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


TOML_SIMPLE_ESCAPES = {
    "b": "\b",
    "t": "\t",
    "n": "\n",
    "f": "\f",
    "r": "\r",
    '"': '"',
    "\\": "\\",
}


def toml_unescape_key(raw: str) -> str:
    """Decode a TOML basic-string key with the full escape set; raise on rest."""
    out: list[str] = []
    index = 0
    while index < len(raw):
        char = raw[index]
        if char != "\\":
            out.append(char)
            index += 1
            continue
        if index + 1 >= len(raw):
            raise RuntimeError("dangling escape in hooks.state key")
        follower = raw[index + 1]
        if follower in TOML_SIMPLE_ESCAPES:
            out.append(TOML_SIMPLE_ESCAPES[follower])
            index += 2
            continue
        if follower in ("u", "U"):
            width = 4 if follower == "u" else 8
            hexpart = raw[index + 2 : index + 2 + width]
            if len(hexpart) != width or not all(
                c in "0123456789abcdefABCDEF" for c in hexpart
            ):
                raise RuntimeError("invalid unicode escape in hooks.state key")
            out.append(chr(int(hexpart, 16)))
            index += 2 + width
            continue
        raise RuntimeError(f"unsupported escape \\{follower} in hooks.state key")
    return "".join(out)


# TOML allows indented table headers and trailing comments; both are owned
# forms this repairer must recognize or the stale table survives as a
# textual disguise (2026-07-30 third review round).
STATE_HEADER_RE = re.compile(r'^\s*\[hooks\.state\."((?:[^"\\]|\\.)*)"\]\s*(?:#.*)?$')
OWNED_BODY_RE = re.compile(
    r'^\s*(?:enabled\s*=\s*(?:true|false)|trusted_hash\s*=\s*"sha256:[0-9a-f]+")\s*(?:#.*)?$'
)
OWNED_SUFFIX_RE = re.compile(
    r"^(?:"
    + "|".join(re.escape(label) for label in EVENT_LABELS.values())
    + r"):\d+:\d+$"
)


def is_owned_state_key(key: str, hook_file: Path) -> bool:
    prefix = f"{hook_file}:"
    return key.startswith(prefix) and bool(OWNED_SUFFIX_RE.match(key[len(prefix):]))


def strip_owned_state_tables(text: str, hook_file: Path) -> str:
    """Drop every hooks.state table keyed to hook_file, whole tables only.

    An owned table is its header plus the contiguous enabled/trusted_hash
    lines this tool writes. Comments and blank lines after the body belong to
    whatever follows and are preserved. Anything else inside an owned table
    means another writer extended it — refuse instead of guessing, because a
    partial removal would orphan keys into the preceding TOML table.
    """
    lines = text.splitlines(keepends=True)
    kept: list[str] = []
    index = 0
    while index < len(lines):
        header = STATE_HEADER_RE.match(lines[index])
        owned = False
        if header:
            key = toml_unescape_key(header.group(1))
            owned = is_owned_state_key(key, hook_file)
        if not owned:
            kept.append(lines[index])
            index += 1
            continue
        index += 1
        while index < len(lines) and OWNED_BODY_RE.match(lines[index]):
            index += 1
        if index < len(lines):
            boundary = lines[index]
            stripped = boundary.strip()
            if stripped and not stripped.startswith("#") and not stripped.startswith("["):
                raise RuntimeError(
                    "owned hooks.state table contains unexpected content; "
                    "refusing to rewrite trust state"
                )
    return "".join(kept)


def parsed_without_owned_state(parsed: dict, hook_file: Path) -> dict:
    import copy

    clone = copy.deepcopy(parsed)
    state = clone.get("hooks", {}).get("state")
    if isinstance(state, dict):
        for key in list(state):
            if is_owned_state_key(key, hook_file):
                del state[key]
        # Writing the first owned entry materializes hooks.state; an empty
        # leftover container must compare equal to its absence.
        if not state:
            del clone["hooks"]["state"]
        if not clone["hooks"]:
            del clone["hooks"]
    return clone


def sync_trust_set(
    config: Path,
    hook_file: Path,
    entries: list[tuple[str, int, int, str]],
    check: bool,
) -> tuple[bool, str]:
    text = config.read_text(encoding="utf-8")
    # Parser truth first: tomllib decodes every valid header form (escapes,
    # indentation, inline comments), so a stale owned key can never hide
    # behind a textual disguise the line surgery fails to recognize.
    parsed_original = tomllib.loads(text)
    disk_state = parsed_original.get("hooks", {}).get("state", {})
    owned_on_disk = {
        key: value
        for key, value in disk_state.items()
        if isinstance(disk_state, dict) and is_owned_state_key(key, hook_file)
    }
    owned_expected = {}
    # Orca's config writer can preserve this comment while moving table blocks.
    # Remove the comment independently; never infer ownership of the following
    # hook state from comment adjacency.
    base = re.sub(rf"(?m)^{re.escape(STATE_MARKER)}\n?", "", text)
    # Own this hook file's entire hooks.state namespace, not just the current
    # keys: a repair that removes a group (duplicate-guard collapse, shrinking
    # hook lists) must also retire the trust block of the removed index, or a
    # stale trusted hash survives and the next check false-greens.
    base = strip_owned_state_tables(base, hook_file)
    blocks = []
    for event_label, group_index, handler_index, trusted_hash in entries:
        key = f"{hook_file}:{event_label}:{group_index}:{handler_index}"
        owned_expected[key] = {"enabled": True, "trusted_hash": trusted_hash}
        blocks.append(
            f'[hooks.state."{toml_escape_key(key)}"]\n'
            "enabled = true\n"
            f'trusted_hash = "{trusted_hash}"\n'
        )
    expected = base.rstrip() + f"\n\n{STATE_MARKER}\n" + "\n".join(blocks)
    parsed_expected = tomllib.loads(expected)
    # The rewrite may only change owned hooks.state tables. If the surgery
    # damaged anything else (mis-read header, swallowed data), refuse to write.
    if parsed_without_owned_state(parsed_original, hook_file) != parsed_without_owned_state(
        parsed_expected, hook_file
    ):
        raise RuntimeError(
            "trust rewrite would alter unrelated config content; refusing"
        )
    expected_state = parsed_expected.get("hooks", {}).get("state", {})
    if {
        key: value
        for key, value in expected_state.items()
        if is_owned_state_key(key, hook_file)
    } != owned_expected:
        raise RuntimeError(
            "trust rewrite failed to converge owned hooks.state; refusing"
        )
    changed = text != expected or owned_on_disk != owned_expected
    if changed and not check:
        atomic_write(config, expected.encode("utf-8"), mode=0o600)
    return changed, f"trust state {config}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    required = [
        CANONICAL_HOME / "AGENTS.md",
        CANONICAL_HOME / "hooks.json",
        CANONICAL_HOME / "config.toml",
        RUNTIME_HOME / "hooks.json",
        RUNTIME_HOME / "config.toml",
        WSL_BRIDGE_SOURCE,
        WSL_WRAPPER_SOURCE,
    ]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise SystemExit("missing required Codex policy files: " + ", ".join(missing))

    lock_path = RUNTIME_HOME / ".policy-sync.lock"
    with lock_path.open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        group = policy_group()
        trusted_hash = normalized_hook_hash("PreToolUse", group)
        results: list[tuple[bool, str]] = []
        results.extend(sync_wsl_launcher(args.check))
        results.append(sync_agents(args.check))
        hook_changed, hook_label, _guard_index, runtime_hooks = sync_runtime_hooks(
            group, args.check
        )
        results.append((hook_changed, hook_label))
        results.append(
            sync_trust_set(
                CANONICAL_HOME / "config.toml",
                CANONICAL_HOME / "hooks.json",
                [("pre_tool_use", 0, 0, trusted_hash)],
                args.check,
            )
        )
        results.append(
            sync_trust_set(
                RUNTIME_HOME / "config.toml",
                RUNTIME_HOME / "hooks.json",
                runtime_trust_entries(runtime_hooks),
                args.check,
            )
        )

    drift = [label for changed, label in results if changed]
    if not args.quiet:
        print(
            json.dumps(
                {
                    "ok": not drift if args.check else True,
                    "mode": "check" if args.check else "sync",
                    "drift": drift,
                },
                ensure_ascii=False,
            )
        )
    return 1 if args.check and drift else 0


if __name__ == "__main__":
    raise SystemExit(main())
