# Deliver phase

Use for TASK-10, BUILD-10, BUILD-20, and RELEASE-10. BUG-10 and SYNC-10 are request-scoped adjuncts; rerun the Engine afterward and resume its route. The Engine owns exact task fields, statuses, legal transitions, readiness, dependency and waiver checks, attempt bounds, and evidence completeness; `TASKS.md` stores populated project records and does not teach that grammar.

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
- Before completion, run every required formatter, linter, type checker, test,
  build, and applicable security check from the current Harness Profile.

## Tasks and local construction

- Require current Gate B and exact REQ/DES/AUTH basis. Generate dependency-aware tasks with `scripts/task_waves.py`; only dependency-ready `READY` tasks run.
- Apply the Fastlane INVEST profile without task metadata: Independent, Negotiable within DES/AUTH, Valuable, Estimable, Small, and Testable. Prefer a Thin Vertical Slice. A migration-, security-, infrastructure-, or evidence-only task may remain horizontal when that is the coherent outcome. For `NEW_BUILD`, the first wave delivers the approved end-to-end journey; only a bounded disposable spike may precede a blocked path.
- Before a plan becomes `CURRENT`, every approved first-release requirement has exactly one derived disposition: `TASK_COVERED`, `ALREADY_SATISFIED`, or eligible `NOT_APPLICABLE`. Use the Engine's task-coverage projection; never add a second ledger. Coverage repair is Codex work unless it changes approved requirements, design, envelope, or authority.
- Use Red/Green TDD when it provides meaningful executable feedback: Chicago School for state/public behavior and London School for interaction-heavy orchestration. Preserve the failing observation, make the smallest passing change, then refactor. TDD is not required for pure documentation, manifest regeneration, or work whose only useful check is an existing validator. Preserve the Property-Based Testing contract exactly.
- The existing DONE transition is the Fastlane Definition of Done: all acceptance criteria and applicable properties pass; exact validation passed; observed evidence is recorded; work stayed inside REQ/DES/AUTH, write, command, and attempt boundaries; checkpoint state is current; no blocker/placeholder remains; and required documentation/runbook updates are complete.
- The coordinator alone writes. Preserve task IDs, protected paths, attempts, checkpoints, failed evidence, and last-known-green state. Every task keeps one current status, outcome, acceptance list, validation block, execution log, and collapsed exact metadata record. Copy every approved applicable `PROP-*` and required/triggered `HARNESS-*` command into the task validation and record observed results in VERIFY.
- When the owner asks for the next task or its completion evidence, name the exact task, write boundary, focused validation command, broader required command if different, and canonical VERIFY destination from current task metadata. Do not describe a broad command as the focused check, and do not omit the evidence destination.
- An `AGENT_CORRECTION` handoff names the observed defect, the exact current task/write boundary, and every exact validation command and VERIFY destination that Codex will rerun. It remains automatic and owner-free only while all correction work stays inside those current boundaries.
- Local tasks use AWS mode `NONE` or `DOCS_ONLY`. Authenticated work checkpoints local state and hands off to the explicit `operate-fastlane-aws` procedure. Gate B is a planned maximum, never task or account authority.
- For release-readiness or task decisions that depend on a current AWS fact, consult official current AWS Core directly. If unavailable, pause only the affected AWS-specific task with one recovery action; never guess or restart intake.
- Continue automatically while work is current, ready, safe, and bounded. After each reconciled task/wave, rerun the Engine; use its totals and task IDs for owner-visible progress.

## Run, claim, and checkpoint procedure

- Use `scripts/task_waves.py` for every run and task-state mutation. Start either `SINGLE_TASK` or `AUTONOMOUS`, claim exactly one dependency-ready task as coordinator, and record the incremented attempt before editing. Never use isolated worktrees or a second writer.
- A persisted `RUNNING` run is interrupted state. Resume that same run only from its latest Engine-valid checkpoint; never silently start over. Reconcile any `IN_PROGRESS` task to `DONE` or `BLOCKED` before pausing or completing the run.
- Mark `DONE` only with a current local `EV-*` row bound to that task, exact validation, tested commit/worktree/artifact, observed result, time, actor, and durable source. A placeholder, URL alone, wrong task, duplicate, `FAILED`, or `NOT_STARTED` row cannot complete work.
- Preserve every failed property or Harness observation and append the later rerun. Property failures retain the replay seed or exact command, minimized counterexample when available, and one failure classification. A specification change returns to requirements or design; an implementation, test-machine, or environment defect may continue only inside the approved boundary.
- After each reconciled task or safe wave, inspect the integrated diff, record evidence, update the last-known-green commit, append a unique checkpoint, rerun the Engine, and continue or stop from its route. Never commit protected unrelated work or perform an unapproved remote action.

## Bugfix, release, and GitHub adjuncts

- For BUG-10, preserve the observed failure, confirmed evidence, approved repair boundary, intentionally unchanged behavior, and replayable regression check. Project applicable `BUG-PROP-*` records into task validation and VERIFY evidence; do not let a generator or oracle defect masquerade as a product repair. Return to the unchanged Engine route unless the owner changed requirements or design.
- RELEASE-10 compares the exact current REQ/DES/AUTH, task coverage, Harness/property evidence, package, runbook, and any observed AWS evidence. It may record only `NOT_READY`, `READY_TO_DEPLOY`, or `RELEASE_VERIFIED` from deterministic evidence. Planned work, documentation, a submitted request, or local success never becomes deployed proof.
- SYNC-10 runs only for a current owner request naming the repository and GitHub operation, after local work is checkpointed. Perform only the permitted reconciliation, retain `PENDING_SYNC` otherwise, rerun the Engine, and restore its pending owner action.

## AWS handoff and reconciliation

- `operate-fastlane-aws` owns the operational procedure. Keep documentation guidance, authenticated read preflight, mutation authority, append-only mutation journal, reconciliation, rollback, and teardown distinct. Tool availability grants nothing.
- Route deployment AWS-10 → AWS-20 → AWS-30; only AWS-20 may mutate. Route residual verification/teardown AWS-40 → AWS-50 → AWS-40; only AWS-50 may mutate. Use only the phase-appropriate subset of a mutation-capable Gate B envelope.
- Checkpoint local work before handoff. The AWS skill owns operation selection, exact receipt validation, pre-call journal entries, terminal results, independent read reconciliation, retry, journal closure, residual disposition, and teardown. Never duplicate that procedure in TASKS, VERIFY, RUNBOOK, or this reference.

## Teardown and residuals

- Follow `aws_residual_disposition`, never raw lifecycle intent. While the projection is PENDING, ask for one set-level choice for the complete current residual set: `RETAIN`, `INVESTIGATE`, or `REMOVE`. RETAIN stops with retained-resource evidence; INVESTIGATE requires separate AWS-40 read authority; REMOVE proceeds only toward a separately authorized teardown.
- Every choice after `RESIDUALS_REMAIN` must be strictly newer than that evidence. After READY, RETAIN and INVESTIGATE must be strictly newer, while an earlier owner-provenanced TEARDOWN may carry forward as REMOVE. New residual evidence reopens the choice. Never ask separately for each residual.
- REMOVE plus `RESIDUALS_REMAIN` refreshes AWS-40 first. REMOVE plus `READY_FOR_TEARDOWN` may present the full canonical teardown receipt template for owner completion. Lifecycle intent itself never authorizes account access.
- Stop only for failed validation, stale state, exhausted attempts, changed scope, missing external authority, or another declared boundary. SYNC-10 may perform only the current authorized GitHub adjunct, then reruns and restores the Engine route.
