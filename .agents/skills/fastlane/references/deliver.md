# Deliver phase

Use for TASK-10, BUILD-10, BUILD-20, and RELEASE-10. BUG-10 and SYNC-10
remain current-request-scoped adjunct prompts, not Engine routes; after either
adjunct, rerun the Engine and resume its derived route.

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
- Before a modern task plan becomes `CURRENT`, require exactly one derived
  disposition for every approved first-release requirement. `TASK_COVERED`
  requires at least one non-`SKIPPED` task with the exact current REQ,
  requirement ID, and canonical acceptance ID trace. `ALREADY_SATISFIED`
  requires current-scoped concrete `LOCAL_PASS` or `VERIFIED` Verification
  matrix evidence with `Task IDs: NONE`. `NOT_APPLICABLE` is allowed only for
  an `OPTIONAL_FEATURE` requirement with current-scoped concrete no-task
  evidence.
- Use the Engine's additive `tasks.requirement_coverage_complete`,
  `tasks.requirement_coverage`, and `tasks.missing_requirement_ids` projection;
  never create a second coverage ledger or task metadata field. Missing or
  mismatched coverage is Codex-owned task replanning. Ask the owner only if the
  correction requires a material change to the approved requirement, design,
  construction envelope, or authority.

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
- Generate and execute local tasks with AWS mode `NONE` or `DOCS_ONLY` only.
  A Gate B `READ_ONLY` or `MUTATE_LISTED_RESOURCES` value is a maximum planned
  ceiling for later AWS phases, never task authority. When a task reaches an
  authenticated AWS boundary, checkpoint its local state and route read-only
  preflight through AWS-10, deployment mutation through AWS-20, reconciliation
  through AWS-30/AWS-40, and teardown mutation through AWS-50. Never relabel a
  task as `READ_ONLY` or `MUTATION`.
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
  preflight, mutation authority, mutation journaling, and reconciliation
  separate. Search current AWS documentation and retrieve exact returned skills
  without account access; obtain the exact read-only preflight receipt before
  touching the named account; record authenticated reads as `RUNNING`, `READY`,
  `BLOCKED`, or `STALE`; and present mutation authority only after a current
  matching `READY` observation. Before the AWS-20 call, append a STARTED row
  to VERIFY's canonical `AWS deployment action and reconciliation evidence`
  table with immutable deployment provenance from the exact receipt, or the
  exact current construction `AUTH-*`, parsed Gate B expiry timestamp, and Gate
  B authorization source for fast-dev;
  afterward append exactly one terminal `SUCCEEDED`, `FAILED`,
  `PARTIAL`, or `UNKNOWN` row using the canonical identifiers/result grammar
  and route to AWS-30. That grammar structures evidence but does not prove
  execution. STARTED is not proof that AWS received the call. If only STARTED
  exists, keep owner action NONE, append UNKNOWN, rerun the Engine, and only then
  request AWS-30 read authority. Failed, partial, or unknown attempts must be
  reconciled before any retry. AWS-30 uses independently current exact read
  authority, never inherited mutation authority. While Gate B remains current,
  an exact still-current AWS-10 receipt may be reused when it already covers
  the reconciliation reads. Only restricted stale or expired closure requires
  a fresh post-action read receipt. AWS-30 appends `COMPLETE`, `BLOCKED`, or
  `STALE`. One first STALE may be followed by one
  later COMPLETE or BLOCKED under a different current read authorization; a
  repeated STALE is a safety-review blocker, and nothing follows COMPLETE or
  BLOCKED. COMPLETE or BLOCKED returns to RELEASE-10, while the first STALE
  remains AWS-30. Each AWS-30 row stores `Read authority source` exactly as
  `SOURCE: <stable owner-message source>; AUTHORIZED_AT: <ISO 8601 with
  timezone>; RESOURCES: <exact canonical list>; OPERATIONS: <exact canonical
  list>`. `AUTHORIZED_AT` is the `Observed at` timestamp of the matching Read-only
  preflight row in Action authorization provenance, not the owner-message
  creation time or the AWS-30 evidence-row observation time. The AWS-30 row
  observation stays inside the authorization window, Resources exactly match
  the stored authorized resources, and observed read operations are a subset of
  stored operations. A current terminal row matches the current
  receipt tuple; an acknowledged historical row is validated from its stored
  tuple after the marked receipt expires or is replaced. COMPLETE IDs resolve
  exactly once to current VERIFIED Verification
  matrix rows with concrete requirement/invariant and AWS/manual evidence, plus
  Artifact/environment exactly
  `ARTIFACT: sha256:<64 lowercase>; ACCOUNT: <exact>; REGION: <exact>; ENVIRONMENT: <exact>`.
  RELEASE-10 loads both this journal and Current release decision; acknowledged
  history remains auditable. RELEASE-10 stores the
  terminal AWS-30 Evidence ID as Active evidence cutoff; once acknowledged it
  cannot reroute. Retry requires distinct current mutation authority: a new exact
  deployment receipt for explicit-gate or freshly approved construction
  authorization for fast-dev, plus a new Attempt ID. A read-only receipt permits only its exact reads and never deployment or teardown. For a
  mutation-capable Gate B envelope, ensure `AWS allowed operations` contains the union of exact
  preflight/reconciliation reads and later mutation or teardown operations; use
  only the phase-appropriate subset. Follow `aws_execution.progress_state`
  rather than the legacy compatibility boolean.
- If Gate B expires or becomes legitimately stale after a valid STARTED row,
  close the immutable attempt rather than dropping it or reviving the envelope.
  Follow only `deployment_journal_closure_authority`, which is restricted to
  `docs/project/VERIFY.md` and the Engine-selected bounded operation: append an
  UNKNOWN journal row; record the canonical marked read receipt/provenance and
  append its AWS-30 journal row; or atomically update the RELEASE-10 release
  decision and evidence cutoff. A BLOCKED reconciliation permits only
  `NOT_READY`; stale-basis COMPLETE also permits only `NOT_READY`; same-basis
  COMPLETE permits `NOT_READY` or `RELEASE_VERIFIED`. Only journal rows are
  append-only. Ordinary write authority, construction authorization, and
  external mutation authority remain NONE. A fresh exact post-action read
  receipt may authorize the historical attempt's bounded AWS-30 reads, but it
  cannot renew Gate B. The immutable STARTED row must also bind durable proof
  that it did not precede its original deployment authorization. Do not apply
  this narrow exception when STARTED
  occurred after expiry, when the attempt or evidence is malformed, or when a
  consumed attempt is merely marked READY_TO_DEPLOY again. A consumed
  `NOT_READY` attempt stops at `RELEASE_REVIEW_BLOCKED` for owner safety review;
  it does not loop automatically through RELEASE-10.
- Every concrete AWS-40 row stores `Read authority source` exactly as `SOURCE:
  <stable owner-message source>; AUTHORIZED_AT: <ISO 8601 with timezone>`.
  `AUTHORIZED_AT` is the `Observed at` timestamp of the matching Read-only
  preflight row in Action authorization provenance. Current reads stay inside
  the receipt window and scope. Exact resource/operation equality is required
  only when the Engine projects exact-scope reconciliation; other current rows
  may observe a subset, and STALE never claims fresh reads. A later receipt
  expiry or replacement does not invalidate a terminal row whose durable tuple
  was proven at append time.
- Follow `aws_residual_disposition`, not the raw lifecycle value. When that
  projection is PENDING, ask for one outcome for the complete current residual
  set: RETAIN stores `RETAIN` and stops; INVESTIGATE stores `RESIDUAL_REVIEW`
  and requires separate read authority for AWS-40; REMOVE stores `TEARDOWN`.
  REMOVE with current READY evidence may present the exact separate teardown
  receipt; REMOVE after `RESIDUALS_REMAIN` first refreshes through AWS-40. Every
  choice after `RESIDUALS_REMAIN` must be strictly newer than that evidence.
  After READY, RETAIN and INVESTIGATE must be strictly newer, while an earlier
  owner-provenanced TEARDOWN may carry forward as REMOVE. New residual evidence
  reopens the choice.
- Pause only on validation failure, stale state, exhausted attempts, scope
  change, missing external authority, or another declared stop condition.
- Route deployment through AWS-10 to AWS-20 to AWS-30; only AWS-20 may mutate.
  Route teardown through AWS-40 to AWS-50 to AWS-40; only AWS-50 may mutate.
  Invoke SYNC-10 only as a
  current-request-scoped adjunct for GitHub operations in the approved envelope
  or current explicit owner request, then rerun and resume the Engine route.
