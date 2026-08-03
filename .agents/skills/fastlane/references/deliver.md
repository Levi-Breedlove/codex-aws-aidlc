# Deliver phase

Use for TASK-10, BUILD-10, BUILD-20, and RELEASE-10. BUG-10 and SYNC-10 are request-scoped adjuncts; rerun the Engine afterward and resume its route.

## Application source layout

- New greenfield application source lives under singular `app/`. Do not create
  a parallel `apps/` or another application source tree. Keep tests under
  `tests/` and infrastructure under `infrastructure/`; root toolchain files may
  remain at the repository root when the selected stack requires them.
- Brownfield work preserves the existing source root recorded in the approved
  baseline and write boundary. Never introduce `app/` or `apps/` as a parallel
  tree unless a design-controlled change explicitly approves the migration.
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
- The coordinator alone writes. Preserve task IDs, protected paths, attempts, checkpoints, failed evidence, and last-known-green state. Copy every required or triggered `HARNESS-*` command into the task's existing Validation section and record results in VERIFY.
- Local tasks use AWS mode `NONE` or `DOCS_ONLY`. Authenticated work checkpoints local state and hands off to the explicit `operate-fastlane-aws` procedure. Gate B is a planned maximum, never task or account authority.
- For release-readiness or task decisions that depend on a current AWS fact, consult official current AWS Core directly. If unavailable, pause only the affected AWS-specific task with one recovery action; never guess or restart intake.
- Continue automatically while work is current, ready, safe, and bounded. After each reconciled task/wave, rerun the Engine; use its totals and task IDs for owner-visible progress.

## AWS handoff and reconciliation

- `operate-fastlane-aws` owns the operational procedure. Keep documentation guidance, authenticated read preflight, mutation authority, append-only mutation journal, reconciliation, rollback, and teardown distinct. Tool availability grants nothing.
- Route deployment AWS-10 → AWS-20 → AWS-30; only AWS-20 may mutate. Route residual verification/teardown AWS-40 → AWS-50 → AWS-40; only AWS-50 may mutate. Use only the phase-appropriate subset of a mutation-capable Gate B envelope.
- Before AWS-20, append one immutable STARTED record. After the observable call, append exactly one terminal `SUCCEEDED`, `FAILED`, `PARTIAL`, or `UNKNOWN` record, then reconcile through AWS-30. STARTED is not proof that AWS received a call. A lone STARTED becomes UNKNOWN before any owner action. Failed, partial, and unknown attempts reconcile before retry; retry needs a new attempt and distinct current mutation authority.
- AWS-30 has independent read authority and never inherits mutation authority. Its source is exactly `SOURCE: <stable owner-message source>; AUTHORIZED_AT: <ISO 8601 with timezone>; RESOURCES: <exact canonical list>; OPERATIONS: <exact canonical list>`. `AUTHORIZED_AT` comes from the matching Read-only preflight row in Action authorization provenance. The observation remains within that window; resources match and observed operations stay within the stored set. Exact equality is required only for exact-scope reconciliation; STALE never claims fresh reads.
- AWS-30 appends one `COMPLETE`, `BLOCKED`, or `STALE`. One first STALE may be followed by COMPLETE/BLOCKED under different current read authority; repeated STALE requires safety review. COMPLETE/BLOCKED returns to RELEASE-10. Current COMPLETE IDs resolve to current VERIFIED matrix evidence bound to exact artifact, account, Region, and environment. RELEASE-10 records the terminal evidence cutoff so an acknowledged attempt cannot reroute.
- If Gate B expires or legitimately stales after a valid STARTED record, use only the Engine's bounded journal-closure authority. It may append UNKNOWN, record a fresh exact post-action read receipt and reconciliation, or update the release decision/cutoff. It never restores construction or mutation authority. Invalid timing, malformed evidence, or replay fails closed.
- AWS-40 read provenance is exactly `SOURCE: <stable owner-message source>; AUTHORIZED_AT: <ISO 8601 with timezone>`, tied to its matching Read-only preflight row in Action authorization provenance. Current reads remain in scope; a later receipt expiry does not invalidate a terminal row whose tuple was proven when recorded.

## Teardown and residuals

- Follow `aws_residual_disposition`, never raw lifecycle intent. While the projection is PENDING, ask for one set-level choice for the complete current residual set: `RETAIN`, `INVESTIGATE`, or `REMOVE`. RETAIN stops with retained-resource evidence; INVESTIGATE requires separate AWS-40 read authority; REMOVE proceeds only toward a separately authorized teardown.
- Every choice after `RESIDUALS_REMAIN` must be strictly newer than that evidence. After READY, RETAIN and INVESTIGATE must be strictly newer, while an earlier owner-provenanced TEARDOWN may carry forward as REMOVE. New residual evidence reopens the choice. Never ask separately for each residual.
- REMOVE plus `RESIDUALS_REMAIN` refreshes AWS-40 first. REMOVE plus `READY_FOR_TEARDOWN` may present the exact teardown receipt. Lifecycle intent itself never authorizes account access.
- Stop only for failed validation, stale state, exhausted attempts, changed scope, missing external authority, or another declared boundary. SYNC-10 may perform only the current authorized GitHub adjunct, then reruns and restores the Engine route.
