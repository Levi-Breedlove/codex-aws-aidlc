#!/usr/bin/env python3
"""Configure Fastlane command-line streams for deterministic UTF-8 I/O."""

from __future__ import annotations

import sys
from typing import TextIO


def _reconfigure_utf8(stream: TextIO) -> None:
    """Use strict UTF-8 when a standard stream supports reconfiguration."""

    reconfigure = getattr(stream, "reconfigure", None)
    if callable(reconfigure):
        reconfigure(encoding="utf-8", errors="strict")


def configure_utf8_standard_streams() -> None:
    """Configure stdin, stdout, and stderr without import-time side effects."""

    for stream in (sys.stdin, sys.stdout, sys.stderr):
        _reconfigure_utf8(stream)
