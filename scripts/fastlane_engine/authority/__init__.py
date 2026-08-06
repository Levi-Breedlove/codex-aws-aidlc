"""Fastlane owner, GitHub, and AWS authority evaluation.

Authority modules intersect exact canonical receipts and project boundaries. They
are read-only and never execute GitHub or AWS actions.
"""

from .receipts import (
    current_gate_receipt_contract,
    exact_selection,
    marked_receipt,
    unselected_selection,
    validate_gate_receipt_candidate,
)
from .aws import (
    _deployment_reconciliation_read_authority,
    _read_preflight_receipt_authority,
    _receipt_external_authority,
    _teardown_reconciliation_read_authority,
    build_aws_authority_policy,
    derive_external_authority,
)
from .closure import (
    derive_aws_execution_projection,
    derive_deployment_sequence_state,
    derive_read_preflight_state,
    derive_teardown_sequence_state,
)
from .github import (
    _aws_action_transition_projection,
    derive_aws_mode_boundary,
    derive_current_prompt_aws_mode,
    derive_request_match,
)
from .write import (
    derive_aws_lifecycle_intent_write_authority,
    derive_deployment_journal_closure_authority,
    derive_teardown_journal_closure_authority,
    derive_write_authority,
    lifecycle_intent_record_boundary_is_settled,
)

__all__ = [
    "_aws_action_transition_projection",
    "_deployment_reconciliation_read_authority",
    "_read_preflight_receipt_authority",
    "_receipt_external_authority",
    "_teardown_reconciliation_read_authority",
    "current_gate_receipt_contract",
    "exact_selection",
    "marked_receipt",
    "unselected_selection",
    "validate_gate_receipt_candidate",
    "build_aws_authority_policy",
    "derive_aws_execution_projection",
    "derive_aws_lifecycle_intent_write_authority",
    "derive_aws_mode_boundary",
    "derive_current_prompt_aws_mode",
    "derive_deployment_journal_closure_authority",
    "derive_deployment_sequence_state",
    "derive_external_authority",
    "derive_read_preflight_state",
    "derive_request_match",
    "derive_teardown_journal_closure_authority",
    "derive_teardown_sequence_state",
    "derive_write_authority",
    "lifecycle_intent_record_boundary_is_settled",
]
