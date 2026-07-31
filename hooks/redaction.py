"""Shared secret redaction for exported transcripts, worklogs, and devlogs."""

from __future__ import annotations

import re


_KEY_VALUE = re.compile(
    r"""("""
    r"""appkey|appsecret|access_token|approval_key|hashkey|api_key|api_secret|client_secret|"""
    r"""secret_key|secret|token|password|passwd|authorization|private_key)"""
    r"""(["']?\s*[=:]\s*["']?)([^\s"',}\n]{4,})""",
    re.I,
)
_BEARER = re.compile(r"(?i)\b(bearer\s+)([A-Za-z0-9._~+/\-]{8,}=*)")
_KNOWN_TOKEN = re.compile(
    r"(?<![A-Za-z0-9])("
    r"sk-ant-[A-Za-z0-9_-]{16,}|"
    r"sk-[A-Za-z0-9_-]{16,}|"
    r"ghp_[A-Za-z0-9]{20,}|"
    r"github_pat_[A-Za-z0-9_]{20,}|"
    r"AKIA[0-9A-Z]{16}"
    r")(?![A-Za-z0-9])"
)
_PRIVATE_KEY = re.compile(
    r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?-----END [A-Z0-9 ]*PRIVATE KEY-----",
    re.S,
)
_URL_CREDENTIAL = re.compile(r"(?i)\b(https?://)([^/\s:@]+):([^@/\s]+)@")


def redact(text: str) -> str:
    text = _PRIVATE_KEY.sub("[REDACTED PRIVATE KEY]", text)
    text = _URL_CREDENTIAL.sub(lambda match: match.group(1) + "[REDACTED]@", text)
    text = _BEARER.sub(lambda match: match.group(1) + "[REDACTED]", text)
    text = _KEY_VALUE.sub(lambda match: match.group(1) + match.group(2) + "[REDACTED]", text)
    return _KNOWN_TOKEN.sub("[REDACTED]", text)
