"""Exact byte canonicalization and SHA-256 helpers.

Inputs are caller-owned values or bytes; outputs are deterministic bytes and
digests. The module performs no I/O and never decides lifecycle or authority.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def lf_normalized_text(value: str) -> str:
    """Normalize line endings without changing any other character."""

    return value.replace("\r\n", "\n").replace("\r", "\n")


def lf_normalized_bytes(value: str, *, trailing_lf: bool = False) -> bytes:
    """Encode normalized UTF-8 text with an optional exact trailing LF."""

    text = lf_normalized_text(value)
    if trailing_lf:
        text = text.rstrip("\n") + "\n"
    return text.encode("utf-8")


def canonical_json_bytes(value: Any) -> bytes:
    """Serialize canonical compact JSON using stable key ordering."""

    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def sha256_hex(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_prefixed(value: bytes) -> str:
    return "sha256:" + sha256_hex(value)
