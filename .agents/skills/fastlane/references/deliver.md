# Deliver phase

Use for TASK-10, BUILD-10, BUILD-20, and RELEASE-10.

- Require a current approved Gate B and current REQ/DES/AUTH basis.
- Generate dependency-aware tasks and use `scripts/task_waves.py`; only READY
  tasks with satisfied dependencies may run.
- Tasks trace to approved EARS requirement IDs, but task cards never contain an
  `EARS form` field. Apply the Fastlane INVEST profile without adding metadata:
  Independent means only necessary dependencies and one writer; Negotiable
  means implementation details may vary only within the approved DES/AUTH
  boundary; Valuable means one user- or operator-observable approved outcome;
  Estimable means bounded paths, dependencies, risks, commands, and attempt
  budget; Small means one coherent implementation-and-validation cycle; and
  Testable means objective acceptance criteria and exact validation commands.
- Prefer a Thin Vertical Slice when the selected architecture permits it. Do
  not force vertical slicing on a legitimate migration-only, security-only,
  infrastructure-only, or evidence-only task; it still needs one coherent
  outcome and independent evidence.
- For `NEW_BUILD`, structural wave 1 implements the Gate-B-approved first
  end-to-end journey. One approved disposable spike may precede it only when a
  documented technical unknown blocks the path; the spike cannot satisfy the
  product outcome or replace the earliest non-spike end-to-end task.

- Use Red/Green TDD when it provides meaningful executable feedback: Chicago
  School for state-based behavior and public APIs, or London School for
  interaction-heavy orchestration. Preserve the initial failing observation,
  implement the smallest passing change, then refactor while checks stay green.
  TDD is not required for pure documentation, manifest regeneration, or work
  whose only meaningful check is an existing IaC, policy, package, or
  integration validator. Preserve the Property-Based Testing contract exactly.
- The existing DONE transition is the Fastlane Definition of Done. A task is
  DONE only when all acceptance criteria pass; exact validation ran and passed;
  applicable property tests pass; observed evidence is recorded; work remained
  inside REQ/DES/AUTH and write boundaries; execution log and checkpoint state
  are current; no unresolved blocker or placeholder remains; and required
  documentation and runbook changes are complete.
- The coordinator alone writes code and ledgers. Preserve task IDs, write and
  command boundaries, attempt budgets, checkpoints, and protected paths.
- Run applicable example, property, integration, security, recovery, and IaC
  validation. Record only observed results in VERIFY and operational facts in
  RUNBOOK.
- Copy every required or triggered conditional `HARNESS-*` check into the
  existing task Validation section without adding task metadata. Run its exact
  command or API only within the active REQ/DES/AUTH and external-authority
  boundaries, then record the observation in VERIFY's Harness execution
  evidence. Preserve failed observations, apply the smallest in-scope fix, and
  rerun the same check; route a requirement or design change to its existing
  gate instead of weakening the harness.
- For release-readiness or task decisions that depend on a current AWS fact,
  consult official current AWS Core directly. If unavailable,
  pause only the affected AWS-specific task with one recovery action; never
  guess or restart intake.
- Continue autonomously while work remains current, ready, safe, and inside
  Gate B. After each reconciled task or wave, rerun the Engine and continue in
  the same turn when it returns `NONE_CONTINUE_AUTOMATICALLY`.
- Derive owner-visible task progress only from the Engine's task totals and
  task-ID fields through `fastlane_presenter.py`; never estimate progress from
  narration.
- At READY_TO_DEPLOY, keep AWS documentation guidance, authenticated read-only
  preflight, and mutation authority separate. Search current AWS documentation
  and retrieve exact returned skills without account access; obtain the exact
  read-only preflight receipt before touching the named account; record
  authenticated reads as `RUNNING`, `READY`, `BLOCKED`, or `STALE`; and present
  mutation authority only after a current matching `READY` observation. A
  read-only receipt permits only its exact reads and never deployment or
  teardown. For a mutation-capable Gate B envelope, ensure `AWS allowed
  operations` contains the union of exact preflight/reconciliation reads and
  later mutation or teardown operations; use only the phase-appropriate subset.
  Follow `aws_execution.progress_state` rather than the legacy
  compatibility boolean.
- Pause only on validation failure, stale state, exhausted attempts, scope
  change, missing external authority, or another declared stop condition.
- Route AWS mutation through AWS-10/AWS-20 and GitHub mutation through the
  approved envelope or current explicit owner request.
