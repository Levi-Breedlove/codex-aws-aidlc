"""Fastlane owner, GitHub, and AWS authority evaluation.

Authority modules intersect immutable normalized facts and exact receipts. They
are read-only and never execute GitHub or AWS actions. Compatibility attributes
are loaded lazily so importing an authority model cannot initialize lifecycle
domains or create an import cycle.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any


_EXPORT_MODULES = {
    "_aws_action_transition_projection": ".github",
    "_deployment_reconciliation_read_authority": ".aws",
    "_read_preflight_receipt_authority": ".aws",
    "_receipt_external_authority": ".aws",
    "_teardown_reconciliation_read_authority": ".aws",
    "build_aws_authority_policy": ".aws",
    "current_gate_receipt_contract": ".receipts",
    "derive_aws_lifecycle_intent_write_authority": ".write",
    "derive_aws_mode_boundary": ".github",
    "derive_current_prompt_aws_mode": ".github",
    "derive_deployment_journal_closure_authority": ".write",
    "derive_external_authority": ".aws",
    "derive_request_match": ".github",
    "derive_teardown_journal_closure_authority": ".write",
    "derive_write_authority": ".write",
    "exact_selection": ".receipts",
    "lifecycle_intent_record_boundary_is_settled": ".write",
    "marked_receipt": ".receipts",
    "unselected_selection": ".receipts",
    "validate_gate_receipt_candidate": ".receipts",
}

__all__ = sorted(_EXPORT_MODULES)


def __getattr__(name: str) -> Any:
    """COMPATIBILITY: resolve the historical package-level API on demand."""

    module_name = _EXPORT_MODULES.get(name)
    if module_name is None:
        raise AttributeError(name)
    value = getattr(import_module(module_name, __name__), name)
    globals()[name] = value
    return value
