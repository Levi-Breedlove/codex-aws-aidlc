"""Stable diagnostic values and deterministic collection.

Canonical inputs are registered diagnostic definitions and domain emissions.
The module returns immutable diagnostics in insertion order. It performs no I/O,
routing, remediation, or report serialization, and it cannot broaden authority.
The public diagnostic dictionary remains compatible with Engine report schema 2.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Iterator, Mapping


@dataclass(frozen=True)
class Diagnostic:
    """One report-compatible diagnostic before final ID assignment."""

    code: str
    message: str
    path: str | None = None
    severity: str = "ERROR"

    def to_dict(self, diagnostic_id: str | None = None) -> dict[str, Any]:
        """Return the existing public shape without exposing internal metadata."""

        result: dict[str, Any] = {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
        }
        if diagnostic_id is not None:
            result["diagnostic_id"] = diagnostic_id
        if self.path is not None:
            result["path"] = self.path
        return result


@dataclass(frozen=True)
class DiagnosticDefinition:
    """Internal ownership metadata that does not change the public report."""

    code: str
    category: str
    default_owner: str
    remediation_category: str
    automatic_correction_eligible: bool = False


class DiagnosticCollector:
    """Append diagnostics deterministically and reject unknown strict emissions."""

    def __init__(
        self,
        definitions: Mapping[str, DiagnosticDefinition] | None = None,
        *,
        strict: bool = False,
        initial: Iterable[Diagnostic] = (),
        backing: list[Diagnostic] | None = None,
    ) -> None:
        self._definitions = dict(definitions or {})
        self._strict = strict
        if backing is not None and tuple(initial):
            raise ValueError("Use either initial diagnostics or a mutable backing list")
        self._items = backing if backing is not None else list(initial)

    def _append(
        self,
        code: str,
        message: str,
        path: str | None,
        severity: str,
    ) -> None:
        if self._strict and code not in self._definitions:
            raise ValueError(f"Unknown diagnostic code: {code}")
        self._items.append(Diagnostic(code, message, path, severity))

    def error(self, code: str, message: str, path: str | None = None) -> None:
        """Append an error without assigning its final report ID."""

        self._append(code, message, path, "ERROR")

    def warning(self, code: str, message: str, path: str | None = None) -> None:
        """Append a warning without assigning its final report ID."""

        self._append(code, message, path, "WARNING")

    @property
    def has_errors(self) -> bool:
        return any(item.severity == "ERROR" for item in self._items)

    def append(self, diagnostic: Diagnostic) -> None:
        if not isinstance(diagnostic, Diagnostic):
            raise TypeError("DiagnosticCollector accepts only Diagnostic values")
        if self._strict and diagnostic.code not in self._definitions:
            raise ValueError(f"Unknown diagnostic code: {diagnostic.code}")
        self._items.append(diagnostic)

    def extend(self, diagnostics: Iterable[Diagnostic]) -> None:
        for diagnostic in diagnostics:
            self.append(diagnostic)

    def freeze(self) -> tuple[Diagnostic, ...]:
        return tuple(self._items)

    def __iter__(self) -> Iterator[Diagnostic]:
        return iter(self._items)

    def __len__(self) -> int:
        return len(self._items)

    def __getitem__(self, index: int) -> Diagnostic:
        return self._items[index]
