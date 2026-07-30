#!/usr/bin/env python3
from __future__ import annotations

import base64
import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("sync-orca-codex-home.py")
SPEC = importlib.util.spec_from_file_location("sync_orca_codex_home", SCRIPT)
assert SPEC and SPEC.loader
SYNC = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SYNC)


class OrcaBridgeTrustTest(unittest.TestCase):
    def test_exact_known_bridge_variants_are_accepted(self):
        paths = [
            SYNC.HOME / ".orca/agent-hooks/codex-hook.sh",
            SYNC.RUNTIME_HOME / ".orca/agent-hooks/codex-hook.sh",
        ]
        for path in paths:
            commands = SYNC.orca_bridge_commands(path)
            self.assertEqual(len(commands), 4)
            for command in commands:
                self.assertTrue(SYNC.expected_orca_bridge(command))

    def test_bridge_near_misses_are_rejected(self):
        path = SYNC.HOME / ".orca/agent-hooks/codex-hook.sh"
        command = next(iter(SYNC.orca_bridge_commands(path)))
        self.assertFalse(SYNC.expected_orca_bridge(command + "; true"))
        self.assertFalse(
            SYNC.expected_orca_bridge(command.replace("codex-hook.sh", "other.sh"))
        )

    def test_runtime_shape_remains_fail_closed(self):
        path = SYNC.HOME / ".orca/agent-hooks/codex-hook.sh"
        bridge = sorted(SYNC.orca_bridge_commands(path))[-1]
        guard = {
            "matcher": "^Bash$",
            "hooks": [
                {
                    "type": "command",
                    "command": SYNC.POLICY_COMMAND,
                    "timeout": 5,
                    "statusMessage": "Checking command safety",
                }
            ],
        }
        hooks = {
            "SessionStart": [
                {"hooks": [{"type": "command", "command": bridge, "timeout": 10}]}
            ],
            "PreToolUse": [guard],
        }
        self.assertEqual(len(SYNC.runtime_trust_entries(hooks)), 2)

        hooks["SessionStart"][0]["hooks"][0]["timeout"] = 11
        with self.assertRaisesRegex(RuntimeError, "refusing to trust"):
            SYNC.runtime_trust_entries(hooks)


class RuntimeHooksOrderAgnosticTest(unittest.TestCase):
    """sync_runtime_hooks must accept the canonical guardrail at any index."""

    CANONICAL = {
        "matcher": "^Bash$",
        "hooks": [
            {
                "type": "command",
                "command": SYNC.POLICY_COMMAND,
                "timeout": 5,
                "statusMessage": "Checking command safety",
            }
        ],
    }
    BRIDGE = {"hooks": [{"type": "command", "command": "/bin/sh bridge.sh", "timeout": 10}]}

    def setUp(self):
        import json
        import tempfile

        self._json = json
        self._tmp = tempfile.TemporaryDirectory()
        self._orig_runtime_home = SYNC.RUNTIME_HOME
        SYNC.RUNTIME_HOME = Path(self._tmp.name)
        self.addCleanup(self._restore)

    def _restore(self):
        SYNC.RUNTIME_HOME = self._orig_runtime_home
        self._tmp.cleanup()

    def _write(self, groups):
        payload = self._json.dumps({"hooks": {"PreToolUse": groups}})
        (Path(self._tmp.name) / "hooks.json").write_text(payload, encoding="utf-8")

    def _read_groups(self):
        data = self._json.loads(
            (Path(self._tmp.name) / "hooks.json").read_text(encoding="utf-8")
        )
        return data["hooks"]["PreToolUse"]

    def test_orca_order_guard_first_is_accepted(self):
        self._write([self.CANONICAL, self.BRIDGE])
        changed, _, guard_index, _ = SYNC.sync_runtime_hooks(self.CANONICAL, check=True)
        self.assertFalse(changed)
        self.assertEqual(guard_index, 0)

    def test_legacy_order_guard_last_is_accepted(self):
        self._write([self.BRIDGE, self.CANONICAL])
        changed, _, guard_index, _ = SYNC.sync_runtime_hooks(self.CANONICAL, check=True)
        self.assertFalse(changed)
        self.assertEqual(guard_index, 1)

    def test_missing_guard_is_appended(self):
        self._write([self.BRIDGE])
        changed, _, guard_index, _ = SYNC.sync_runtime_hooks(self.CANONICAL, check=False)
        self.assertTrue(changed)
        self.assertEqual(guard_index, 1)
        self.assertEqual(self._read_groups(), [self.BRIDGE, self.CANONICAL])

    def test_content_drift_is_replaced_in_place(self):
        stale = self._json.loads(self._json.dumps(self.CANONICAL))
        stale["hooks"][0]["timeout"] = 99
        self._write([stale, self.BRIDGE])
        changed, _, guard_index, _ = SYNC.sync_runtime_hooks(self.CANONICAL, check=False)
        self.assertTrue(changed)
        self.assertEqual(guard_index, 0)
        self.assertEqual(self._read_groups(), [self.CANONICAL, self.BRIDGE])

    def test_duplicate_guards_collapse_to_first_position(self):
        dup = self._json.loads(self._json.dumps(self.CANONICAL))
        self._write([self.BRIDGE, self.CANONICAL, dup])
        changed, _, guard_index, _ = SYNC.sync_runtime_hooks(self.CANONICAL, check=False)
        self.assertTrue(changed)
        self.assertEqual(guard_index, 1)
        self.assertEqual(self._read_groups(), [self.BRIDGE, self.CANONICAL])

    def test_empty_pretooluse_appends_guard(self):
        self._write([])
        changed, _, guard_index, _ = SYNC.sync_runtime_hooks(self.CANONICAL, check=False)
        self.assertTrue(changed)
        self.assertEqual(guard_index, 0)
        self.assertEqual(self._read_groups(), [self.CANONICAL])

    def test_guard_command_under_other_event_fails_closed(self):
        hooks = {
            "SessionStart": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": SYNC.POLICY_COMMAND,
                            "timeout": 5,
                        }
                    ]
                }
            ],
            "PreToolUse": [self.CANONICAL],
        }
        with self.assertRaisesRegex(RuntimeError, "guardrail hook shape changed"):
            SYNC.runtime_trust_entries(hooks)


class TrustNamespaceOwnershipTest(unittest.TestCase):
    """sync_trust_set must retire stale trust keys of removed hook indices."""

    HOOK_FILE = Path("/tmp/claude/testhome/hooks.json")
    HASH = "sha256:" + "ab" * 32

    def setUp(self):
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        self.config = Path(self._tmp.name) / "config.toml"
        self.addCleanup(self._tmp.cleanup)

    def _write_config(self, extra_blocks: str = ""):
        self.config.write_text(
            'model = "gpt-test"\n' + extra_blocks, encoding="utf-8"
        )

    def test_stale_index_block_is_flagged_and_purged(self):
        stale = (
            f'[hooks.state."{self.HOOK_FILE}:pre_tool_use:2:0"]\n'
            "enabled = true\n"
            f'trusted_hash = "{self.HASH}"\n'
        )
        self._write_config(stale)
        entries = [("pre_tool_use", 1, 0, self.HASH)]
        changed, _ = SYNC.sync_trust_set(self.config, self.HOOK_FILE, entries, check=True)
        self.assertTrue(changed, "stale trust key must be reported as drift")
        SYNC.sync_trust_set(self.config, self.HOOK_FILE, entries, check=False)
        text = self.config.read_text(encoding="utf-8")
        self.assertNotIn(":pre_tool_use:2:0", text)
        self.assertIn(":pre_tool_use:1:0", text)
        changed_after, _ = SYNC.sync_trust_set(
            self.config, self.HOOK_FILE, entries, check=True
        )
        self.assertFalse(changed_after)

    def test_foreign_hook_file_blocks_are_preserved(self):
        foreign = (
            '[hooks.state."/other/hooks.json:pre_tool_use:0:0"]\n'
            "enabled = true\n"
            f'trusted_hash = "{self.HASH}"\n'
        )
        self._write_config(foreign)
        entries = [("pre_tool_use", 0, 0, self.HASH)]
        SYNC.sync_trust_set(self.config, self.HOOK_FILE, entries, check=False)
        text = self.config.read_text(encoding="utf-8")
        self.assertIn("/other/hooks.json:pre_tool_use:0:0", text)
        self.assertIn(f"{self.HOOK_FILE}:pre_tool_use:0:0", text)

    def test_unknown_key_in_owned_table_fails_closed(self):
        blocks = (
            "[other.table]\n"
            'value = "keep"\n'
            f'[hooks.state."{self.HOOK_FILE}:pre_tool_use:3:0"]\n'
            "enabled = true\n"
            f'trusted_hash = "{self.HASH}"\n'
            'surprise_key = "orca-added"\n'
            "[another.table]\n"
            'value = "keep2"\n'
        )
        self._write_config(blocks)
        entries = [("pre_tool_use", 0, 0, self.HASH)]
        original = self.config.read_text(encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "unexpected content"):
            SYNC.sync_trust_set(self.config, self.HOOK_FILE, entries, check=False)
        self.assertEqual(
            self.config.read_text(encoding="utf-8"),
            original,
            "refusal must not modify the file",
        )

    def test_backslash_hook_file_keys_round_trip(self):
        win_file = Path("C:\\Users\\t\\hooks.json")
        stale_key_escaped = SYNC.toml_escape_key(f"{win_file}:pre_tool_use:9:0")
        self._write_config(
            f'[hooks.state."{stale_key_escaped}"]\n'
            "enabled = true\n"
            f'trusted_hash = "{self.HASH}"\n'
        )
        entries = [("pre_tool_use", 0, 0, self.HASH)]
        SYNC.sync_trust_set(self.config, win_file, entries, check=False)
        text = self.config.read_text(encoding="utf-8")
        self.assertNotIn(":pre_tool_use:9:0", text)
        self.assertIn(SYNC.toml_escape_key(f"{win_file}:pre_tool_use:0:0"), text)
        changed, _ = SYNC.sync_trust_set(self.config, win_file, entries, check=True)
        self.assertFalse(changed, "escaped keys must round-trip idempotently")

    def test_colon_suffixed_foreign_namespace_is_preserved(self):
        lookalike = (
            f'[hooks.state."{self.HOOK_FILE}:backup/hooks.json:pre_tool_use:0:0"]\n'
            "enabled = true\n"
            f'trusted_hash = "{self.HASH}"\n'
        )
        self._write_config(lookalike)
        entries = [("pre_tool_use", 0, 0, self.HASH)]
        SYNC.sync_trust_set(self.config, self.HOOK_FILE, entries, check=False)
        text = self.config.read_text(encoding="utf-8")
        self.assertIn(":backup/hooks.json:pre_tool_use:0:0", text)

    def test_adjacent_tables_without_blank_lines_are_repairable(self):
        blocks = (
            f'[hooks.state."{self.HOOK_FILE}:pre_tool_use:5:0"]\n'
            "enabled = true\n"
            f'trusted_hash = "{self.HASH}"\n'
            "[keep.me]\n"
            'value = "adjacent"\n'
        )
        self._write_config(blocks)
        entries = [("pre_tool_use", 0, 0, self.HASH)]
        changed, _ = SYNC.sync_trust_set(self.config, self.HOOK_FILE, entries, check=False)
        self.assertTrue(changed)
        text = self.config.read_text(encoding="utf-8")
        self.assertNotIn(":pre_tool_use:5:0", text)
        self.assertIn('[keep.me]\nvalue = "adjacent"', text)
        changed_after, _ = SYNC.sync_trust_set(
            self.config, self.HOOK_FILE, entries, check=True
        )
        self.assertFalse(changed_after)

    def test_unsupported_escape_fails_closed(self):
        self.assertEqual(SYNC.toml_unescape_key("\\u0041bc"), "Abc")
        self.assertEqual(SYNC.toml_unescape_key("a\\tb"), "a\tb")
        with self.assertRaisesRegex(RuntimeError, "unsupported escape"):
            SYNC.toml_unescape_key("bad\\q")
        with self.assertRaisesRegex(RuntimeError, "invalid unicode escape"):
            SYNC.toml_unescape_key("\\u12zz")

    def test_indented_owned_header_is_still_owned(self):
        stale = (
            f'  [hooks.state."{self.HOOK_FILE}:pre_tool_use:9:0"]\n'
            "  enabled = true\n"
            f'  trusted_hash = "{self.HASH}"\n'
        )
        self._write_config(stale)
        entries = [("pre_tool_use", 0, 0, self.HASH)]
        changed, _ = SYNC.sync_trust_set(self.config, self.HOOK_FILE, entries, check=True)
        self.assertTrue(changed, "indented stale header must be flagged")
        SYNC.sync_trust_set(self.config, self.HOOK_FILE, entries, check=False)
        self.assertNotIn(":pre_tool_use:9:0", self.config.read_text(encoding="utf-8"))

    def test_owned_header_with_inline_comment_is_still_owned(self):
        stale = (
            f'[hooks.state."{self.HOOK_FILE}:pre_tool_use:9:0"] # written by orca\n'
            "enabled = true\n"
            f'trusted_hash = "{self.HASH}"\n'
        )
        self._write_config(stale)
        entries = [("pre_tool_use", 0, 0, self.HASH)]
        changed, _ = SYNC.sync_trust_set(self.config, self.HOOK_FILE, entries, check=True)
        self.assertTrue(changed, "commented stale header must be flagged")
        SYNC.sync_trust_set(self.config, self.HOOK_FILE, entries, check=False)
        self.assertNotIn(":pre_tool_use:9:0", self.config.read_text(encoding="utf-8"))

    def test_foreign_unicode_escaped_key_survives_without_crash(self):
        foreign = (
            '[hooks.state."\\u0041-foreign/hooks.json:pre_tool_use:0:0"]\n'
            "enabled = true\n"
            f'trusted_hash = "{self.HASH}"\n'
        )
        self._write_config(foreign)
        entries = [("pre_tool_use", 0, 0, self.HASH)]
        SYNC.sync_trust_set(self.config, self.HOOK_FILE, entries, check=False)
        text = self.config.read_text(encoding="utf-8")
        self.assertIn("\\u0041-foreign/hooks.json:pre_tool_use:0:0", text)

    def test_comment_between_owned_block_and_next_table_survives(self):
        blocks = (
            f'[hooks.state."{self.HOOK_FILE}:pre_tool_use:9:0"]\n'
            "enabled = true\n"
            f'trusted_hash = "{self.HASH}"\n'
            "# documentation for the next table\n"
            "[keep.me]\n"
            'value = "adjacent"\n'
        )
        self._write_config(blocks)
        entries = [("pre_tool_use", 0, 0, self.HASH)]
        SYNC.sync_trust_set(self.config, self.HOOK_FILE, entries, check=False)
        text = self.config.read_text(encoding="utf-8")
        self.assertIn("# documentation for the next table", text)
        self.assertIn('[keep.me]\nvalue = "adjacent"', text)
        self.assertNotIn(":pre_tool_use:9:0", text)

    def test_semantic_guard_blocks_damaging_surgery(self):
        """Mutation-red for the parser guard: a rewrite that touches anything
        outside the owned namespace must be refused before the write."""
        self._write_config("[foreign.data]\nvalue = \"important\"\n")
        entries = [("pre_tool_use", 0, 0, self.HASH)]
        original = self.config.read_text(encoding="utf-8")
        real_strip = SYNC.strip_owned_state_tables

        def damaging_strip(text, hook_file):
            return real_strip(text, hook_file).replace(
                'value = "important"', 'value = "x"'
            )

        SYNC.strip_owned_state_tables = damaging_strip
        try:
            with self.assertRaisesRegex(RuntimeError, "unrelated config"):
                SYNC.sync_trust_set(self.config, self.HOOK_FILE, entries, check=False)
        finally:
            SYNC.strip_owned_state_tables = real_strip
        self.assertEqual(
            self.config.read_text(encoding="utf-8"),
            original,
            "guard must refuse before writing",
        )

    def test_format_drift_with_correct_semantics_is_flagged(self):
        """Mutation-red for the text arm: semantically correct owned entries in
        a non-canonical text form (no managed marker) must still be drift."""
        key = f"{self.HOOK_FILE}:pre_tool_use:0:0"
        self._write_config(
            f'[hooks.state."{key}"]\n'
            "enabled = true\n"
            f'trusted_hash = "{self.HASH}"\n'
        )
        entries = [("pre_tool_use", 0, 0, self.HASH)]
        changed, _ = SYNC.sync_trust_set(self.config, self.HOOK_FILE, entries, check=True)
        self.assertTrue(changed, "non-canonical text must be flagged even when semantics match")
        SYNC.sync_trust_set(self.config, self.HOOK_FILE, entries, check=False)
        changed_after, _ = SYNC.sync_trust_set(
            self.config, self.HOOK_FILE, entries, check=True
        )
        self.assertFalse(changed_after)

    def test_multiline_array_brackets_are_not_headers(self):
        blocks = (
            "[foreign.data]\n"
            "list = [\n"
            '  "a",\n'
            '  ["nested", "x"],\n'
            "]\n"
        )
        self._write_config(blocks)
        entries = [("pre_tool_use", 0, 0, self.HASH)]
        SYNC.sync_trust_set(self.config, self.HOOK_FILE, entries, check=False)
        import tomllib

        parsed = tomllib.loads(self.config.read_text(encoding="utf-8"))
        self.assertEqual(parsed["foreign"]["data"]["list"], ["a", ["nested", "x"]])
        changed, _ = SYNC.sync_trust_set(self.config, self.HOOK_FILE, entries, check=True)
        self.assertFalse(changed)


class WslLauncherRenderTest(unittest.TestCase):
    def test_launcher_marker_is_preserved_without_plaintext_path(self):
        launcher = r"C:\Users\test\AppData\Local\Programs\orca\resources\bin\orca.exe"
        encoded = base64.b64encode(launcher.encode()).decode()
        current = f"# ORCA_WIN_LAUNCHER_B64={encoded}\n"
        template = (
            f"# ORCA_WIN_LAUNCHER_B64={SYNC.LAUNCHER_B64_TOKEN}\n"
            f"VALUE='{SYNC.LAUNCHER_B64_TOKEN}'\n"
        )
        rendered = SYNC.render_wsl_wrapper(current, template).decode()
        self.assertEqual(rendered.count(encoded), 2)
        self.assertNotIn(launcher, rendered)

    def test_invalid_launcher_marker_is_rejected(self):
        encoded = base64.b64encode(b"/tmp/not-orca").decode()
        with self.assertRaisesRegex(RuntimeError, "not an Orca executable"):
            SYNC.launcher_b64_from_wrapper(
                f"# ORCA_WIN_LAUNCHER_B64={encoded}\n"
            )


if __name__ == "__main__":
    unittest.main()
