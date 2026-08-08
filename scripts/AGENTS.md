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

## Modular Engine boundaries

- Keep `bootstrap_doctor.py` as the stable public command and compatibility
  facade. Lifecycle policy belongs under `fastlane_engine/`; new callers use
  its supported API rather than importing CLI internals.
- Normal evaluation consumes one immutable project snapshot. `core.snapshot`
  owns bounded filesystem and trusted read-only Git observation; domain
  validators do not read files, run Git, call subprocesses, write state, or
  access GitHub or AWS.
- Source-assisted Define observes one explicitly named repository-relative
  UTF-8 brief through the same bounded snapshot primitive. Its pure Define
  projection may classify candidate facts and technical proposals, but it must
  emit no raw secret-like content, perform no write, alter no lifecycle report,
  and grant no approval or authority.
- `define`, `design`, `deliver`, and `aws` own their domain validation.
  `authority` owns exact receipt and envelope intersections. `orchestration`
  composes immutable results; `routing` selects the next route; `remediation`
  assigns safe correction responsibility; `report` alone serializes schema 2.
- Keep presentation, optional hooks, initialization, package production, and
  task mutation outside lifecycle domains. `task_waves.py` remains the sole task
  mutator and consumes the public Engine Delivery API; it never loads the
  doctor CLI.
- `fastlane_adr.py` observes bounded ADR files and delegates pure evaluation to
  Design. ADRs cannot select architecture, alter design digests, approve a
  gate, or grant authority.
- Preserve report schema 2, diagnostic order, exact receipt bytes, CLI flags,
  exit codes, and documented compatibility facades unless a separate contract
  explicitly authorizes a migration.
- Characterize complete reports and performance before moving any remaining
  compatibility responsibility. Every new runtime Engine module must satisfy
  import boundaries and every package control inventory.

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
