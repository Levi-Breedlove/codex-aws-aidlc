# Fastlane release qualification procedure

Use this maintainer-only procedure after source changes are coherent. It proves
the exact candidate tree; it grants no merge, release, settings, or AWS
authority.

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
