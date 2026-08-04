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

Require repository precheck, Python 3.11-3.13, Windows, and macOS jobs on the
exact candidate commit. Any correction after a package build, rendered review,
role-play, or CI run invalidates the affected evidence and requires a fresh run
against the new exact head.

Record only sanitized aggregate results, exact commit and package digests,
test counts, documented skips, CI jobs, and honest limitations. Deterministic,
rendered, or model evidence never proves independent human comprehension or a
real AWS deployment, rollback, recovery, or teardown.
