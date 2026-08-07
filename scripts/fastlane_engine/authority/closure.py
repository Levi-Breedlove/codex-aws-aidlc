"""Compatibility exports for bounded local journal-closure authority.

Canonical inputs are normalized AWS journal projections. Returned mappings allow
only exact local VERIFY updates; they never invoke AWS or widen owner authority.
The implementation remains in ``authority.write`` until its callers migrate.
"""

from .write import (
    derive_deployment_journal_closure_authority,
    derive_teardown_journal_closure_authority,
)


__all__ = (
    "derive_deployment_journal_closure_authority",
    "derive_teardown_journal_closure_authority",
)
