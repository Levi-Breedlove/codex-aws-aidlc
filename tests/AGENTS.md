# Verification Engineering Guide

These instructions apply under `tests/` and inherit the root `AGENTS.md`.
This guide narrows the root rules and never widens approval or authorization.

## Plain-language summary

Prove what a user or operator can observe. Show that approved behavior works,
unapproved behavior is denied, invalid input is handled safely, and failures do
not create a false success. Never weaken an assertion merely to obtain a pass.

## Agent reference — exact test rules

- Test externally observable behavior rather than private implementation details.
- Implement approved PRD properties with the language-appropriate property-based testing framework.
- Preserve the seed, reproduction command, and minimized counterexample for a failing property.
- Classify a failure as implementation, specification, generator/oracle, or environment before correcting it.
- Never narrow a generator, weaken an oracle, delete a counterexample, or change an approved invariant merely to pass.
- Rerun the property and relevant example/regression tests after correction.
- Cover happy paths, invalid input, authentication, authorization, boundaries, concurrency, and failures.
- Distinguish unit, integration, end-to-end, security, reliability, performance, and AWS environment tests.
- Do not weaken, delete, or skip assertions merely to make tests pass.
- Use synthetic fixtures without real credentials, secrets, or personal data.
- Make AWS tests safe, scoped, repeatable, and cost-aware.
- Use mocks for local confidence, but do not treat mocks as deployed integration proof.
- Record meaningful release evidence in `../docs/project/VERIFY.md`.
- Reference test suites or reports rather than listing every test case in Markdown.

## Engine parity rules

- Freeze complete normalized reports before extracting a lifecycle domain.
  Normalize only repository roots, the bounded test clock, package-version
  mirrors, and deliberately synthetic Git identities.
- Preserve diagnostic IDs and order, messages, paths, routes, owner actions,
  continuation, remediation, authority, projections, receipts, human output,
  and exit codes exactly unless an approved contract changes them.
- Bind every parity-corpus scenario to at least one named regression test. Do
  not replace an exact assertion with a scenario label or coverage percentage.
- Keep benchmark results ephemeral and machine-local. Repository fixtures may
  store thresholds and structural baselines, never machine paths, usernames,
  raw transcripts, credentials, AWS identifiers, or timing claims from a
  different tree.
