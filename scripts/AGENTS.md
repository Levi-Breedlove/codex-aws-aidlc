# Fastlane Engine Maintenance Guide

These instructions apply under `scripts/` and inherit the root `AGENTS.md`.
This guide narrows the root rules and never widens approval or authorization.

## Plain-language summary

Fastlane scripts are the local control plane for setup, lifecycle routing, task
state, validation, manifest integrity, and packaging. Keep them deterministic,
cross-platform, fail-closed, and free of hidden external actions.

## Agent reference: exact engine rules

- Use the Python standard library unless an approved requirement explicitly
  changes the runtime contract.
- Never install software, change Codex plugin or hook state, inspect credentials,
  access AWS, mutate GitHub, or launch another client from a Fastlane script.
- Preserve documented command-line arguments, exit behavior, and JSON fields.
  Additive schema changes require tests and matching documentation.
- Canonicalize paths, reject unsafe overlap and symlink traversal, preserve
  brownfield files, and use atomic writes for tracked lifecycle state.
- Keep manifest inventory, source hashes, package bytes, and checksums
  deterministic. A stale or unexpected source file fails closed.
- Derive Fastlane Engine and setup status from repository evidence. Never infer human
  approval, AWS authority, plugin trust, or deployed success.
- `task_waves.py` may return or claim only `READY` tasks with satisfied
  dependencies. Preserve legal transitions, bounded attempts, monotonic IDs,
  coordinator ownership, checkpoints, and resumable state.
- Reconcile every `IN_PROGRESS` task before pausing. Inspect a persisted
  `RUNNING` state before resuming; never blindly repeat an external action.
- After a validated task or wave, record the observed command, result, actor,
  time, tested revision or artifact, durable source, and evidence status in
  `../docs/project/VERIFY.md`. Run the Engine before the next wave.

## Engine extraction boundaries

- Characterize complete public reports, diagnostics, routes, receipts, CLI
  behavior, and performance before moving an Engine responsibility.
- Keep `bootstrap_doctor.py` as the stable public command and compatibility
  facade. Internal lifecycle policy belongs under `fastlane_engine/` only after
  its characterization checkpoint passes.
- Normal domain evaluation consumes one immutable project snapshot. Domain
  validators do not read files, run Git, call subprocesses, write state, or
  access GitHub or AWS.
- Keep presentation, optional hooks, initialization, package production, and
  task mutation outside lifecycle domains. `task_waves.py` remains the sole task
  mutator and must eventually consume only a stable pure Engine task API.
- Preserve report schema 2, diagnostic order, exact receipt bytes, exit codes,
  and current compatibility facades unless a separate contract explicitly
  authorizes a migration.
- `fastlane_engine.define` owns pure intake, requirements, assumptions,
  adaptive coverage, change impact, brownfield, AWS-materiality, and Gate A
  readiness evaluation. The public doctor remains a compatibility facade and
  supplies already-observed text and selections.
- `fastlane_engine.design` owns pure architecture, technology, source,
  interface/state, diagram, Harness, envelope, and ADR-rationale evaluation.
  `fastlane_adr.py` observes bounded ADR files and delegates evaluation; it
  cannot select architecture or affect design digests or authority.

## Required validation

For an affected script, run its focused tests and then:

```text
python -m unittest discover -s tests -v
python scripts/update_manifest.py --check
python scripts/package_release.py --check
git diff --check
```

For canonical customer-package maintenance, also run `python
scripts/package_release.py --check --base-commit <exact-base-commit>`. The
comparison is read-only and requires a strict version increase when package
bytes or inventory change; it never grants tag, release, or publication authority.

When source files intentionally change, update the manifest with
`python scripts/update_manifest.py --write` before running the checks.
