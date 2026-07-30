#!/usr/bin/env python3

import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("redaction.py")
SPEC = importlib.util.spec_from_file_location("redaction", SCRIPT)
assert SPEC and SPEC.loader
REDACTION = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REDACTION)
redact = REDACTION.redact


class RedactionTest(unittest.TestCase):
    def test_key_value_and_bearer(self):
        source = "password=hunter2 Authorization: Bearer abcdefghijklmnop"
        result = redact(source)
        self.assertNotIn("hunter2", result)
        self.assertNotIn("abcdefghijklmnop", result)

    def test_known_token_prefixes(self):
        values = [
            "sk-ant-" + "a" * 24,
            "sk-" + "b" * 24,
            "ghp_" + "c" * 36,
            "github_pat_" + "d" * 30,
            "AKIA" + "E" * 16,
        ]
        result = redact(" ".join(values))
        for value in values:
            self.assertNotIn(value, result)
        self.assertEqual(result.count("[REDACTED]"), len(values))

    def test_private_key_and_url_password(self):
        source = (
            "https://alice:swordfish@example.com/path\n"
            "-----BEGIN PRIVATE KEY-----\nSECRET\n-----END PRIVATE KEY-----"
        )
        result = redact(source)
        self.assertNotIn("swordfish", result)
        self.assertNotIn("SECRET", result)

    def test_non_secret_text_survives(self):
        source = "token budget is 1200 and password policy requires MFA"
        self.assertEqual(redact(source), source)


if __name__ == "__main__":
    unittest.main()
