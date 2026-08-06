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
- Domain extraction tests must prove the public doctor and Engine API resolve
  to the same pure implementation, and that domain modules cannot observe or
  mutate repositories, Git, GitHub, AWS, clocks, or external processes.
- Design extraction must preserve every Gate B decision, diagram semantic and
  rendered digest, source-disposition rule, Harness binding, AWS evidence
  requirement, and exact receipt. Moving an unchanged diagram or evaluating an
  ADR may not stale Gate B or grant authority.
- Delivery extraction must preserve task readiness, dependency and waiver
  semantics, attempts, checkpoints, property and completion evidence, release
  state, resume behavior, and the sole-mutator boundary. `task_waves.py` must
  use the public Engine API without dynamically loading the doctor CLI.
- AWS extraction must preserve linked AWS Core evidence, every journal row and
  transition, residual disposition, read/deployment/teardown receipt binding,
  diagnostic order, and restricted closure. Tests remain synthetic and must
  prove that the AWS domain performs no account call or authority broadening.
