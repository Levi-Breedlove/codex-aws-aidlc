# Fastlane release qualification procedure

Use this maintainer-only procedure after source changes are coherent. It proves
the exact candidate tree; it grants no merge, release, settings, or AWS
authority.

## Definition of complete

Completion is a named, evidence-bound claim, not one global state. This policy
creates no lifecycle gate or authority and does not change task-level `DONE`.

- `FRAMEWORK_RELEASE_QUALIFIED` means the exact release head passed the current
  compatibility, manifest, deterministic-package, Golden, role-play,
  performance, rendered-review, and advertised-platform qualification.
- `PROJECT_TARGET_COMPLETE(target)` binds one project target to current evidence:
  `LOCAL` requires E2; `AWS_READ` requires E2 + E3; `DEPLOYED` requires E2 + E3
  + E4; and `RECOVERY` requires E2 + E3 + E4 + E5.
  For `RECOVERY`, E5 must record rollback or restore; teardown-only evidence
  does not qualify `RECOVERY`.
- `AWS_LANE_FIELD_QUALIFIED(lane)` means one named lane has current observed
  deployment, failure or unknown-result reconciliation, recovery, cost,
  separately authorized teardown, and residual-state evidence.
- `PRODUCT_FIELD_VALIDATED` means framework qualification, the independent
  pilot, and the named AWS lane bind the same release head and package digest.

A failed or unobserved higher target does not erase a lower target that remains
current and proven. Other AWS lanes remain unqualified. The current candidate may claim
`PRODUCT_FIELD_VALIDATED` only when the exact head is framework-qualified,
validated by 5-8 first-time, non-author participants, field-qualified through
one separately authorized disposable AWS lane, has no open P0/P1 truth defect,
and has no expired complexity exception.

## Lock the candidate

1. Record the exact base commit, candidate commit, version, prompt-contract
   digest, and package inventory.
2. Confirm the diff stays inside the validated maintenance scope and that every
   version mirror is synchronized.
3. Compare Gate A, Gate B, AWS read, deployment, and teardown receipt bytes with
   the locked compatibility baseline.

## Deterministic evidence

Run focused tests before the complete suite. Then require manifest parity,
`git diff --check`, compilation and indentation checks, pinned Ruff lint and
format checks, two byte-identical package builds, and package comparison against
the exact base commit.

Verify Python 3.11 or newer and an external trusted Git executable in the test
process environment before discovery. Save full failure logs and classify
environment, implementation, specification, and fixture failures separately.
Documentation and stale-version checks use the repository source inventory;
ignored backups and generated output are not product sources and are never
deleted to obtain a pass. Extracted templates use their manifest inventory.

Exercise the extracted template through prerequisites, initialization, resume,
Engine routing, one-question intake, both gates, task readiness, greenfield,
brownfield, infrastructure-only, correction, side-question, overlap, privacy,
and hook-disabled behavior. Hooks may be checked only with harmless fixtures.

Keep the frozen pre-refactor report oracle unchanged. A separate qualification
oracle may add complete current-architecture reports and typed state-machine
projections, but its owner-facing expectations must be written independently
from the production projection. Every deployment and teardown terminal state
must remain bound to a named executable regression.

Complexity exceptions are explicit records, never magic comments or docstring
prefixes. Each record names one symbol, its reviewed measurements, strict
maximums, rationale, reviewed version, and expiry or justified permanent state.
Any new overage, unrecorded growth, or expired exception fails qualification.

## Rendered and role-play evidence

Render the untouched template plus representative Design-stage greenfield,
brownfield, and infrastructure-only records. Inspect first-screen scanning,
navigation, disclosures, diagrams, and authorization wording. Captures must be
sanitized and contain no machine path, account identifier, credential, or
session state.

Run every current schema-5 role-play scenario three times. Release-mode evidence
requires two pseudonymous scorecards per run and adjudication when scores differ
by more than one point. Keep the complete bundle outside the reusable template
and validate it with `scripts/model_roleplay_eval.py`.

## Exact-head closure

Alpha packages use GitHub prereleases with an explicit versioned release link.
Keep the title, prerelease flag, tag, package version, assets, and customer download
link aligned; GitHub's latest-release discovery excludes prereleases. A metadata
correction preserves existing tags and asset bytes and requires provider readback.

Run the deterministic checks above on the exact candidate in one clean,
supported local or Codespaces environment and record the observed operating
system and Python version. Hosted CI, operating-system matrices, and
multi-version matrices are not release gates. Additional platform results may
be recorded only when they were actually observed; synthetic setup tests do not
prove execution on that operating system. Any correction after a package build,
rendered review, role-play, or local qualification run invalidates the affected
evidence and requires a fresh run against the new exact head.

The package's declared Python range is a compatibility contract, not evidence
that every supported interpreter and platform was rerun. The release record
must name each advertised combination that was not observed; one environment
must never be described as cross-platform coverage.

Record only sanitized aggregate results, exact commit and package digests,
test counts, documented skips, the observed environment, and honest
limitations. Deterministic, rendered, or model evidence never proves
independent human comprehension or a real AWS deployment, rollback, recovery,
or teardown.
