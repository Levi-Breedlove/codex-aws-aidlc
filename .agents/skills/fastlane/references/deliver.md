# Deliver phase

Use for TASK-10, BUILD-10/20, RELEASE-10; rerun the Engine after BUG-10/SYNC-10. The Engine owns exact task fields, legal transitions, readiness, dependencies, waivers, attempt bounds, and evidence. `TASKS.md` stores records and does not teach that grammar.

## Application source layout

- Follow the approved `Application source disposition`. Greenfield application
  work uses singular `app/`; its walking-skeleton task must write there. Never
  create parallel `apps/` or `src/` trees. Keep tests under `tests/` and
  infrastructure under `infrastructure/`; root toolchain files may remain at
  the repository root when the selected stack requires them.
- Infrastructure-only work may omit `app/` only when Gate B records exactly
  `NOT_APPLICABLE — INFRASTRUCTURE_ONLY`.
- Brownfield work preserves only the source roots recorded in the approved
  baseline, preservation contract, disposition, and write boundary. Never
  introduce `app/`, `apps/`, or `src/` as a parallel tree unless a
  design-controlled change explicitly approves the migration.
- Follow the selected framework and module boundaries. Separate business logic
  from transport, persistence, and provider integration; validate bounded input
  at the boundary; enforce authorization server-side; keep logging structured
  and safe; and make timeouts and retries explicit.
- Preserve approved interfaces unless a current requirement changes them. Test
  success, invalid input, authorization, boundaries, concurrency, and dependency
  failure. Never put AWS credentials or privileged AWS logic in client code.
- Before completion, run every required check in the current Harness Profile.

## Tasks and local construction

- Require current Gate B and exact REQ/DES/AUTH basis. Use `scripts/task_waves.py`; run only dependency-ready `READY` tasks.
- Apply INVEST: Independent, Negotiable within DES/AUTH, Valuable, Estimable, Small, Testable. Prefer a Thin Vertical Slice; coherent migration, security, infrastructure, or evidence work may be horizontal. For `NEW_BUILD`, the first wave delivers the approved journey; only a bounded disposable spike may precede a blocked path.
- Before `CURRENT`, the Engine must derive `TASK_COVERED`, `ALREADY_SATISFIED`, or eligible `NOT_APPLICABLE` for every approved first-release requirement. No second ledger. Repair coverage automatically within current requirements, design, envelope, and authority.
- Use Red/Green TDD for meaningful executable feedback: Chicago School for public behavior, London School for interaction-heavy orchestration. Preserve failure, make the smallest passing change, then refactor. Documentation, manifest regeneration, and existing-validator-only work need no TDD. Preserve the Property-Based Testing contract.
- DONE requires passing acceptance, properties, and exact validation; observed evidence; compliance with REQ/DES/AUTH, write, command, and attempt boundaries; a current checkpoint; no blockers/placeholders; and required documentation/runbook updates.
- Only the coordinator writes. Preserve IDs, protected paths, attempts, checkpoints, failures, and last-known-green state. Keep one status, outcome, acceptance list, validation block, execution log, and collapsed metadata record per task. Copy applicable `PROP-*` and required/triggered `HARNESS-*` commands into validation; record results in VERIFY.
- For next-task or completion questions, name the current exact task, write boundary, focused and broader required commands, and canonical VERIFY destination.
- An `AGENT_CORRECTION` handoff names the observed defect, current task/write boundary, every exact rerun command, and VERIFY destination. Continue only within those boundaries.
- Local tasks use AWS mode `NONE` or `DOCS_ONLY`. Authenticated work checkpoints local state and hands off to the explicit `operate-fastlane-aws` procedure. Gate B is a planned maximum, never task or account authority.
- For release-readiness or task decisions that depend on a current AWS fact, consult official current AWS Core directly. If unavailable, pause only the affected AWS-specific task with one recovery action; never guess or restart intake.
- Continue automatically while work is current, ready, safe, and bounded. After each reconciled task/wave, rerun the Engine; use its totals and task IDs for owner-visible progress.

## Run, claim, and checkpoint procedure

- Use `scripts/task_waves.py` for every run and task-state mutation. Start either `SINGLE_TASK` or `AUTONOMOUS`, claim exactly one dependency-ready task as coordinator, and record the incremented attempt before editing. Never use isolated worktrees or a second writer.
- A persisted `RUNNING` run is interrupted state. Resume that same run only from its latest Engine-valid checkpoint; never silently start over. Reconcile any `IN_PROGRESS` task to `DONE` or `BLOCKED` before pausing or completing the run.
- Mark `DONE` only with a current local `EV-*` row bound to that task, exact validation, tested commit/worktree/artifact, observed result, time, actor, and durable source. Reject placeholders, URLs alone, wrong tasks, duplicates, `FAILED`, and `NOT_STARTED`.
- Preserve every failed property or Harness observation and append the later rerun. Property failures retain the replay seed or exact command, minimized counterexample when available, and one failure classification. A specification change returns to requirements or design; an implementation, test-machine, or environment defect may continue only inside the approved boundary.
- After each reconciled task or safe wave, inspect the integrated diff, record evidence, update the last-known-green commit, append a unique checkpoint, rerun the Engine, and continue or stop from its route. Never commit protected work or perform an unapproved remote action.

## Bugfix, release, and GitHub adjuncts

- For BUG-10, preserve the observed failure, confirmed evidence, approved repair boundary, intentionally unchanged behavior, and replayable regression check. Project applicable `BUG-PROP-*` records into task validation and VERIFY evidence; do not let a generator or oracle defect masquerade as a product repair. Return to the unchanged Engine route unless the owner changed requirements or design.
- RELEASE-10 compares the exact current REQ/DES/AUTH, task coverage, Harness/property evidence, package, runbook, and any observed AWS evidence. It may record only `NOT_READY`, `READY_TO_DEPLOY`, or `RELEASE_VERIFIED` from deterministic evidence. Planned work, documentation, a submitted request, or local success never becomes deployed proof.
- SYNC-10 runs only for a current owner request naming the repository and GitHub operation, after local work is checkpointed. Perform only the permitted reconciliation, retain `PENDING_SYNC` otherwise, rerun the Engine, and restore its pending owner action.

## AWS handoff and reconciliation

- `operate-fastlane-aws` owns the operational procedure. Keep documentation guidance, authenticated read preflight, mutation authority, append-only mutation journal, reconciliation, rollback, and teardown distinct. Tool availability grants nothing.
- Route deployment AWS-10 → AWS-20 → AWS-30; only AWS-20 may mutate. Route residual verification/teardown AWS-40 → AWS-50 → AWS-40; only AWS-50 may mutate. Use only the phase-appropriate subset of a mutation-capable Gate B envelope.
- Checkpoint before handoff. The AWS skill owns selection, receipts, journal, results, independent reconciliation, retry, closure, residuals, and teardown. Do not duplicate its procedure in project records or this reference.

## Teardown and residuals

- Follow `aws_residual_disposition`, never raw lifecycle intent. While the projection is PENDING, ask for one set-level choice for the complete current residual set: `RETAIN`, `INVESTIGATE`, or `REMOVE`. RETAIN stops with retained-resource evidence; INVESTIGATE requires separate AWS-40 read authority; REMOVE proceeds only toward a separately authorized teardown.
- Every choice after `RESIDUALS_REMAIN` must be strictly newer than that evidence. After READY, RETAIN and INVESTIGATE must be strictly newer, while an earlier owner-provenanced TEARDOWN may carry forward as REMOVE. New residual evidence reopens the choice. Never ask separately for each residual.
- REMOVE plus `RESIDUALS_REMAIN` refreshes AWS-40 first. REMOVE plus `READY_FOR_TEARDOWN` may present the full canonical teardown receipt template for owner completion. Lifecycle intent itself never authorizes account access.
- Stop at failed evidence, stale scope, exhausted attempts, or a declared authority boundary.


## Design 9 checks

Copy applicable LOCAL_BUILD CHECK rows exactly under `#### Validation`,
include its command in the command fence, and write acceptance on one line:
`- [ ] AC-...: <exact criterion> [CHECK: CHECK-...]`. Cover every LOCAL_BUILD check
across the current plan; generic checkboxes cannot replace canonical outcomes.

Preserve the mutator's `Check attempt <n>: RUN=<run>; STARTED=<time>` record;
DONE appends `; ENDED=<time>` at full precision. Metadata edits never extend it.
VERIFY's Exact task check results bind fingerprint, REQ/DES/AUTH, run, attempt,
EV, and elapsed seconds. Fingerprint: SHA-256 of UTF-8 compact JSON
`["FASTLANE_CHECK_V1", ...cells]`, preserving Unicode and column order. Index all
matching attempt observations. Observed at is command completion; subtract
elapsed time to check its start. Both must fall within the attempt. The latest
result must pass within its limit, be cited, and identify one completion artifact.

Before release readiness, Exact local check results bind every LOCAL_RELEASE
check to current Design digest, REQ/DES/AUTH, passing local cutoff EV, artifact,
exact command, elapsed time, timestamp, durable source, and status. Latest results
must pass. Keep failures in one table. A validated AWS cutoff may advance the
active scope; never rewrite the local anchor or relabel stale proof.
