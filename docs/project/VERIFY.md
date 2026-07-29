# My AWS Project — Verification and Release Evidence

`docs/project/VERIFY.md` records observed proof, not plans or authorization. Gate A and Gate B
remain the only routine human gates. The checks below determine construction and
release readiness inside the current approved envelope; they are not additional
human gates.

## Active evidence scope

| Field | Value |
|---|---|
| Workload | My AWS Project |
| Release | TODO |
| Release state | `NOT_READY` |
| Requirements revision | `REQ-0001` |
| Design revision | `DES-0001` |
| Construction authorization | `AUTH-0001` |
| Run ID | `NONE` |
| Checkpoint | `NONE` |
| Commit, tag, or image digest | TODO |
| Evidence cutoff | TODO (ISO 8601 with timezone) |
| Environment | TODO |
| AWS account alias or non-secret ID | TODO / `NOT_APPLICABLE` |
| Region | {{AWS_REGION}} / `NOT_APPLICABLE` |
| Last reviewed | TODO |
| Reviewer | TODO |

These values identify the evidence set; they do not grant repository, GitHub,
or AWS authority. All external actions remain conditional on the current AUTH.

## Evidence status vocabulary

| Status | Meaning |
|---|---|
| `NOT_STARTED` | No implementation or evidence exists |
| `IMPLEMENTED` | Code exists; verification is incomplete |
| `LOCAL_PASS` | Required local checks passed for the identified revision |
| `PENDING_AWS` | Required live AWS or external evidence has not been observed |
| `VERIFIED` | Required evidence passed for the identified artifact and environment |
| `FAILED` | Verification ran and failed |
| `BLOCKED` | A known dependency prevents verification |
| `STALE` | Earlier evidence no longer matches the current revision, artifact, environment, or target state |
| `NOT_APPLICABLE` | Excluded with an explicit rationale |

`STALE` never satisfies a readiness check. A task may be `DONE` when its
authorized task-level local criteria pass while a required live check remains
`PENDING_AWS`; the release remains not ready until that evidence is observed.

### Evidence levels

| Level | Meaning | Minimum attributable basis |
|---|---|---|
| `E0_PROPOSED` | Recommendation or planned control only | Current PRD or task ID |
| `E1_SOURCE_VERIFIED` | Current official source supports the material claim | Current AWS Core or authoritative source evidence ID |
| `E2_LOCALLY_VALIDATED` | Exact local code, test, policy, IaC, or package check passed | Command, artifact/revision, and evidence ID |
| `E3_AWS_READ_OBSERVED` | Authorized read-only AWS observation confirms the target state | Account/Region scope and AWS evidence ID |
| `E4_DEPLOYED_OBSERVED` | Authorized deployment and smoke evidence confirms deployed behavior | Deployment authority, artifact/plan, and evidence ID |
| `E5_RECOVERY_OBSERVED` | Rollback, restore, or teardown behavior was exercised | Recovery/teardown authority and evidence ID |

Report the highest level actually observed for each material claim, with its evidence
IDs and limits. Levels are not approval, are not automatically cumulative across
different claims, and never turn a design recommendation into deployed proof.

## Evidence rules

- Documentation is not implementation evidence, and implementation is not test
  evidence.
- Mocks do not prove live integrations. Local success does not prove AWS
  behavior.
- Every evidence item identifies its requirement/task, command or observation,
  actor, timestamp, commit or digest, environment, result, and durable source.
- Worker receipts are evidence candidates. The coordinator reconciles them
  against changed paths and observed outputs before recording them here.
- Manual evidence says who observed what, when, where, and by which identity,
  without exposing secrets.
- Mark evidence `STALE` when REQ/DES/AUTH, the tested code or artifact, relevant
  configuration, environment, or target state changes.
- Property-based tests prove invariants only within their generated domain and
  do not replace deployed evidence, security review, or recovery rehearsal.
- Preserve failing output, reproduction seeds, and partial external results.
  Never rewrite a failure as not run.
- GitHub and AWS evidence may be read or written only within current AUTH. Use
  `PENDING_SYNC` or `PENDING_AWS` when authority or access is unavailable.

Assign every recorded evidence item one monotonic `EV-nnnn` ID, beginning with
`EV-0001`. Task Evidence fields cite these exact IDs. Requirement, property,
baseline, authorization, and task IDs remain traceability fields, not alternate
evidence-ID formats.

## AWS Core evidence

This ledger proves current runtime skill discovery through official
`aws-core@agent-toolkit-for-aws`; installation metadata, bundled or local
skills, generic connectors, cache, prior conversation, and prose are not proof.
REQ-10 when its materiality is `REQUIRED`, DESIGN-10, and AWS-10 each require
at least one current `AWS-DISC-*` chain:
`search_documentation` records returned canonical skill identifiers, then
`retrieve_skill` records the selected and returned matching identifier.
Multiple chains are allowed only for materially different AWS domains.
Fresh prerequisite capability
observations are ephemeral and never enter this ledger.

Both rows in a chain use the same phase, Discovery ID, Basis IDs, official
source `aws/agent-toolkit-for-aws`, invoked identity, observed semantic plugin
version, actor `CODEX_LIVE_TOOL_CALL`, discovered identifier set, advisory
binding, privacy declarations, and current evidence binding. Retrieval
must not precede search. The selected identifier must be in the search results,
and the returned identifier must equal it. Every material `AWS-EV-*` row in
the PRD cites the `AWS-DISC-*` chain that informed it.

`Basis IDs` are comma-space-separated current stable IDs. REQ-10 includes the
current `REQ-*` plus every affected requirement ID, uses
`NOT_APPLICABLE — requirements feasibility only; no architecture selected` as
its advisory Design binding, and binds Evidence to the current REQ revision.
Its rows always record `Credentials inspected: NO` and `AWS account accessed:
NO`; documentation discovery is not authenticated account preflight.

DESIGN-10 includes the current `DES-*` and binds findings to the design and influenced
technology rows using `DES-0001; TECH: TECH-0001, TECH-0002` or
`DES-0001; TECH: NONE — no technology/toolchain impact`. This trace never
selects a technology, approves Gate B, or authorizes AWS.

Do not record raw skill instructions, tool transcripts, credentials, local
paths, usernames, session identifiers, hook-trust state, secrets, or machine
information. Every passing row records an ISO 8601 time and current binding:
the current DES revision for DESIGN-10 or the Active evidence scope artifact
for AWS-10. AWS-10 uses `ARTIFACT: sha256:<64 lowercase hex>; DES: DES-0001;
TECH: TECH-0001, TECH-0002` or the defined no-impact form.

| Phase | Discovery ID | Basis IDs | Plugin source | Invoked plugin identity | Observed plugin version | Capability | Observation actor | Requested skill | Returned skill identifier | Documentation query | Discovered skill identifiers | Source references | Advisory Design binding | Credentials inspected | AWS account accessed | Observed at | Evidence binding | Observed status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `REQ-10` | `AWS-DISC-0001` | TODO | TODO | TODO | TODO | `search_documentation` | TODO | — | — | `AWS skills for the current requirements-feasibility question` | TODO | TODO | `NOT_APPLICABLE — requirements feasibility only; no architecture selected` | `NO` | `NO` | TODO | TODO | `NOT_STARTED` |
| `REQ-10` | `AWS-DISC-0001` | TODO | TODO | TODO | TODO | `retrieve_skill` | TODO | TODO | TODO | — | TODO | — | `NOT_APPLICABLE — requirements feasibility only; no architecture selected` | `NO` | `NO` | TODO | TODO | `NOT_STARTED` |
| `DESIGN-10` | `AWS-DISC-0002` | TODO | TODO | TODO | TODO | `search_documentation` | TODO | — | — | `AWS skills for the current design question` | TODO | TODO | TODO | `NO` | `NO` | TODO | TODO | `NOT_STARTED` |
| `DESIGN-10` | `AWS-DISC-0002` | TODO | TODO | TODO | TODO | `retrieve_skill` | TODO | TODO | TODO | — | TODO | — | TODO | `NO` | `NO` | TODO | TODO | `NOT_STARTED` |
| `AWS-10` | `AWS-DISC-0003` | TODO | TODO | TODO | TODO | `search_documentation` | TODO | — | — | `AWS skills for the current operational question` | TODO | TODO | TODO | `NO` | `NO` | TODO | TODO | `NOT_STARTED` |
| `AWS-10` | `AWS-DISC-0003` | TODO | TODO | TODO | TODO | `retrieve_skill` | TODO | TODO | TODO | — | TODO | — | TODO | `NO` | `NO` | TODO | TODO | `NOT_STARTED` |

## Read-only AWS preflight evidence

This table records authenticated AWS-10 observations separately from
documentation evidence. A current read receipt must exist before `RUNNING`.
`Account access` is exactly `READ_ONLY` for an attempted authenticated
preflight and `NOT_STARTED` before one. `READY` requires a current unexpired
receipt plus exact matching REQ/DES/AUTH, artifact, profile or role, account,
Region, environment, resources, allowed read operations, caller identity, and
boundary evidence. It grants no mutation. Preserve `BLOCKED` and `STALE`
observations rather than rewriting them as not run.

| Preflight ID | Read authorization | REQ / DES / AUTH | Artifact digest | Role or profile | Account | Region | Environment | Resources | Operations observed | AWS evidence IDs | Account access | Caller identity evidence | Boundary and drift evidence | Started at | Completed at | Identity and boundary match | Result |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `AWS-PREFLIGHT-0001` | TODO | `REQ-0001 / DES-0001 / AUTH-0001` | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | `NOT_STARTED` | TODO | TODO | TODO | TODO | TODO | `NOT_STARTED` |

## IaC validation evidence

Record only observed checks selected by the PRD's current IaC and delivery
validation contract. `TECH IDs` is `TECH: TECH-nnnn, TECH-nnnn` in sorted,
unique order. `Validation method` is exactly `CLOUDFORMATION`, `SAM`, `CDK`,
`TERRAFORM`, `CONTAINER`, or `OTHER`; `OTHER` requires its exact equivalent in
a referenced TECH Validation cell. `Exact command or API` is `COMMAND: <single
local command>` or `API: <service>.<Operation>`. A local/static row uses exactly
`NOT_APPLICABLE — local/static validation` for account, Region, and environment.

An observed binding is exactly `ARTIFACT: sha256:<64 lowercase hex>; PLAN:
sha256:<64 lowercase hex>`, `ARTIFACT: sha256:<64 lowercase hex>; CHANGE_SET:
<exact ARN or ID>; PLAN: sha256:<64 lowercase hex>`, or `ARTIFACT: sha256:<64
lowercase hex>; PLAN: NOT_APPLICABLE — local/static validation`.

| Phase | TECH IDs | Validation method | Exact command or API | Artifact / plan / change-set binding | AWS account | AWS Region | AWS environment | Result | Observed at | Durable source |
|---|---|---|---|---|---|---|---|---|---|---|
| TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | `NOT_STARTED` | TODO | TODO |

Use AWS-10 for authenticated `API: accessanalyzer.ValidatePolicy` evidence.
Use AWS-20 for `API: cloudformation.CreateChangeSet`; creating a change set is
a mutation even though executing it is separate. Do not invent a universal
scanner or substitute a tool not selected by the current TECH register.

## Task completion evidence

This is the machine-checked local evidence ledger for `DONE` transitions. One
unfenced row must exist for every local `EV-nnnn` reference. It names exactly
one task, observed work rather than a plan, the observing actor and time, the
tested commit/worktree/artifact, and a durable local source. `FAILED` preserves
a property-test failure but never satisfies task completion. Only `LOCAL_PASS`
or `VERIFIED` satisfies DONE; a stock, duplicate, wrong-task, `FAILED`,
`NOT_STARTED`, URL-only, or placeholder row does not.

| Evidence ID | Task | Command or observation | Result | Actor | Observed at | Commit / worktree / artifact | Durable source | Status |
|---|---|---|---|---|---|---|---|---|
| EV-0001 | TODO | TODO | TODO | TODO | TODO | TODO | TODO | `NOT_STARTED` |

## Brownfield baseline and regression evidence

Complete this section for brownfield work. For greenfield work, set rows to
`NOT_APPLICABLE`.

| Evidence ID | Baseline commit/environment | Command or observation | Pre-existing result | Post-change result | Attribution and protected behavior | Status |
|---|---|---|---|---|---|---|
| EV-0201 | TODO | TODO | TODO | TODO | TODO | `NOT_STARTED` |

Do not treat a known baseline failure as a new regression, or a newly introduced
failure as accepted debt. If attribution is uncertain, stop affected work and
preserve both states.

## Verification matrix

| Evidence ID | PRD / property IDs | Task IDs | Requirement or invariant | Automated evidence | AWS/manual evidence | Artifact/environment | Status |
|---|---|---|---|---|---|---|---|
| EV-0101 | FR-001 | TODO | Primary outcome succeeds | TODO | TODO | TODO | `NOT_STARTED` |
| EV-0102 | SEC-001, SEC-002, PROP-001 | TODO | Protected operations enforce authentication and authorization | TODO | TODO | TODO | `NOT_STARTED` |
| EV-0103 | REL-001, REL-002, PROP-002, PROP-004 | TODO | Retry and duplicate behavior is safe | TODO | TODO | TODO | `NOT_STARTED` |
| EV-0104 | TODO | TODO | Deployment is repeatable and observable | TODO | TODO | TODO | `NOT_STARTED` |
| EV-0105 | TODO | TODO | Performance target is met | TODO | TODO | TODO | `NOT_STARTED` |
| EV-0106 | TODO | TODO | Budget and cleanup controls are effective | TODO | TODO | TODO | `NOT_STARTED` |

Add rows for material workload risks, not every individual test.

## Harness execution evidence

| Evidence ID | Harness ID | Layer | Basis IDs | Exact command or API | Artifact / environment | Observed result | Observed at | Durable source | Status |
|---|---|---|---|---|---|---|---|---|---|
| EV-0401 | HARNESS-001 | TODO | TODO | TODO | TODO | TODO | TODO | TODO | `NOT_STARTED` |

Add one attributable observation for every required or triggered conditional
Harness Profile row. Record the exact command or API from the current design,
the current REQ/DES/AUTH and task basis, the tested artifact or environment,
the observed result, ISO 8601 time, and durable source. Use `FAILED`,
`LOCAL_PASS`, or `VERIFIED` only for an observed execution; `NOT_STARTED` is
not evidence.

Preserve a failed row and append the later rerun instead of replacing history.
A `NOT_APPLICABLE — <reason>` design row needs no execution evidence and must
not be represented as a false pass. AWS-environment checks run only under the
existing read-only or mutation authority for their exact API and target.
Never record credentials, secret values, private client state, or an inferred
result.

## Property-based test evidence

| Evidence ID | Task ID | REQ / DES / AUTH | Property ID | Framework TECH ID | Framework selection | Observed exact version | Exact command | Observed run | Replay seed or exact command | Minimized counterexample | Failure class / resolution | Result | Observed at | Commit / worktree / artifact | Durable source |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| EV-0001 | TASK-0001 | REQ-0001 / DES-0001 / AUTH-0001 | PROP-001 | TECH-0007 | TODO | TODO | TODO | TODO | TODO | `NONE` | `NONE` | `NOT_STARTED` | TODO | TODO | TODO |

Each row records one attributable execution, never the PRD target. `Observed
run` uses exactly `CASES: <positive integer>; ELAPSED_SECONDS: <non-negative
decimal>`. The evidence ID must be cited by the same task and bind its current
REQ/DES/AUTH trace, selected property framework, exact command, observed ISO
8601 time, commit/worktree/artifact, and durable source. The framework selection
and observed exact version must satisfy the approved `TECH-*` decision. A PASS
must meet the planned case and/or time threshold and record both failure fields
as `NONE`.

For a failure, preserve the smallest observed counterexample and use exactly one
classification: `IMPLEMENTATION_DEFECT`, `SPECIFICATION_AMBIGUITY_OR_DEFECT`,
`GENERATOR_OR_ORACLE_DEFECT`, or `ENVIRONMENT_DEFECT`. Add later evidence
without deleting the failure; a DONE task requires the latest uniquely timed row
for its task/property pair to PASS. Every property row must have a matching Task completion evidence row
with the same EV ID and binding fields; use `FAILED` for
a failed observation and `LOCAL_PASS` or `VERIFIED` for a passing one. A
specification or invariant change
invalidates the affected Gate A or Gate B revision; implementation and
test-machinery corrections may continue only inside the approved construction
boundary.

## Construction and release readiness checks

Only Gate A and Gate B are owner approval gates. Everything below is an
evidence-based readiness check performed within the active authorization.

| Check | Required condition | Status |
|---|---|---|
| Requirements identity | Gate A remains current for the active REQ revision | `NOT_STARTED` |
| Construction identity | Gate B remains current for matching REQ/DES/AUTH IDs | `NOT_STARTED` |
| Architecture | Selected architecture, alternatives, impacts, and traceability remain current | `NOT_STARTED` |
| AWS design grounding | Current DESIGN-10 has fresh successful official AWS Core `retrieve_skill` and `search_documentation` evidence | `NOT_STARTED` |
| Task graph | Dependencies validate, waivers are explicit, and required tasks are complete | `NOT_STARTED` |
| Harness | Every required Harness row has current attributable PASS evidence | `NOT_STARTED` |
| Local evidence | Required local evidence is current, attributable, and at least `E2_LOCALLY_VALIDATED` | `NOT_STARTED` |
| Build | Formatting, linting, typing, tests, and packaging pass | `NOT_STARTED` |
| Infrastructure | IaC, policy, and brownfield drift checks pass | `NOT_STARTED` |
| IaC delivery contract | Every applicable TECH-selected IaC, policy, plan, SBOM, and image check has current attributable evidence | `NOT_STARTED` |
| Security | No unresolved release-blocking security finding remains | `NOT_STARTED` |
| Reliability | Failure, recovery, idempotency, and rollback evidence passes | `NOT_STARTED` |
| Performance | Required targets pass for the identified artifact and environment | `NOT_STARTED` |
| Deployment | Required live deployment and smoke evidence is `VERIFIED` or explicitly not applicable | `NOT_STARTED` |
| Operations | Monitoring, restore, rollback, and authorized cleanup procedures are usable | `NOT_STARTED` |
| Runbook | Deployment, rollback, recovery, and teardown procedures are explicit | `NOT_STARTED` |
| AWS authority | Not required until an AWS action; when present it must be exact and current | `NOT_STARTED` |
| Teardown | Not yet observed, observed under separate authority, or explicitly not applicable | `NOT_STARTED` |
| Package | Manifest and deterministic package checks pass for the current commit | `NOT_STARTED` |
| Model/user pilot | Optional non-sensitive evidence reference and digest, or `NOT_APPLICABLE` with reason | `NOT_STARTED` |
| Cost | Observed and forecast cost remains inside the approved ceiling | `NOT_STARTED` |
| AWS execution grounding | Current AWS-10 has fresh successful official AWS Core operational and deployment evidence before any AWS execution plan | `NOT_STARTED` |

## Autonomous run receipts

The coordinator records one receipt after every safe wave and a final receipt
when the run completes or stops.

| Field | Receipt value |
|---|---|
| Run and checkpoint | TODO |
| REQ / DES / AUTH | `REQ-0001` / `DES-0001` / `AUTH-0001` |
| Tasks completed, blocked, or skipped | TODO |
| Attempts used and remaining | TODO |
| Changed paths and resulting commit/worktree | TODO |
| Commands and observed results | TODO |
| Evidence IDs | TODO |
| GitHub actions | `NONE` / exact authorized actions |
| AWS actions and identifiers | `NONE` / exact authorized actions without secrets |
| Boundary or preservation deviations | `NONE` / TODO |
| Completion or stop reason | TODO |
| Next safe action | TODO |

An AWS submission is not proof of completion. After a deployment, rollback, or
teardown attempt, use read-only evidence to record succeeded, failed, partial,
or unknown state before continuing.

## Reviewed AWS execution contracts

AWS Core selects a currently supported account-operation tool. Use
`STRUCTURED_API` when one attributable operation exposes exact service,
operation, parameters, context, and resources; it needs no execution-contract
row. Use `REVIEWED_SCRIPT` and `AWS-EXEC-*` only for a multi-step workflow
whose exact script or immutable artifact is observable.
This table does not grant authority. A `CURRENT` row must bind to the exact current Gate B or
deployment/teardown authority and to exactly one observable script digest or
immutable reviewed artifact digest. Structured single-operation requests do
not require an execution-contract row.

| Execution ID | Authority kind | Authorization ID | Receipt digest | Script SHA-256 | Immutable artifact SHA-256 | Expected operations | Resources | Account | Region | Environment | Role or profile | Artifact digest | Plan binding | Cost ceiling | Rollback boundary | Valid until | Evidence destination | Status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | `NOT_STARTED` |

Allowed binding kinds are represented by the populated digest column:
`Script SHA-256` binds exact UTF-8 script bytes; `Immutable artifact SHA-256`
binds a separately reviewed immutable script artifact. Put `NONE` in the other
digest column. `Expected operations` and `Resources` must be non-empty subsets
of the current authority. `Valid until` cannot exceed the authority expiry.
Any stale, duplicate, expired, mismatched, or unbound row is diagnostic only
and cannot enable reviewed-script execution. Natural-language descriptions do
not prove script contents.

## Action authorization provenance

This table proves which exact owner message was checked before authenticated
read-only preflight or external mutation; it does not itself authorize an
action or widen Gate B. The stable
source must resolve to the applicable complete verbatim receipt in the uniquely
marked block below, and that receipt must equal the owner's exact message after
trimming only surrounding whitespace. `Role or profile` and `Approver` must
match the receipt and current approved boundary. Recompute `Verbatim receipt
SHA-256` from the exact normalized marked receipt every time any receipt value
changes. A copied, stale, self-authored, or independently typed digest is not
authorization. Read-only preflight authority permits only exact reads; it never
authorizes deployment or teardown.

| Action | Authorization ID | Construction AUTH | Role or profile | Artifact digest | IaC plan/change-set binding | Account / Region / environment | Resources and operations | Cost ceiling and validity | Rollback boundary | Stable owner-message source | Approver | Observed at | Verbatim receipt SHA-256 | Preflight evidence | Identity and boundary match | Result |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Read-only preflight | TODO | `AUTH-0001` | TODO | TODO | `NOT_APPLICABLE — read-only preflight creates no plan` | TODO | TODO | `COST: TODO; BOUNDED_BY: TODO; VALID_UNTIL: TODO` | `NOT_APPLICABLE — no mutation` | TODO | TODO | TODO (ISO 8601 with timezone) | TODO | `NONE` | TODO | `NOT_STARTED` |
| Deployment | TODO | `AUTH-0001` | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO (ISO 8601 with timezone) | TODO | TODO / `NONE` | TODO | `NOT_STARTED` |
| Teardown | TODO | `AUTH-0001` | TODO | `NOT_APPLICABLE — teardown binds the observed inventory` | `NOT_APPLICABLE — teardown uses its removal/retention manifest` | TODO | TODO | TODO | TODO | TODO | TODO | TODO (ISO 8601 with timezone) | TODO | TODO / `NONE` | TODO | `NOT_STARTED` |

For a deployment row, use `sha256:<64 lowercase hex>` for Artifact digest;
`TYPE: <CLOUDFORMATION_CHANGE_SET|TERRAFORM_PLAN|CONTAINER_IMAGE|OTHER>;
IDENTIFIER: <exact identifier>; DIGEST: sha256:<64 lowercase hex>` for the IaC
binding; `ACCOUNT: <value>; REGION: <value>; ENVIRONMENT: <value>`; `RESOURCES:
<comma-separated exact list>; OPERATIONS: <comma-separated exact list>`; and
`COST: <ISO_CURRENCY: amount>; VALID_UNTIL: <ISO 8601 with timezone>`. These
fields mirror the owner receipt and observed preflight; they do not create
authority.

Replace every placeholder in exactly one applicable block only after receiving
that complete owner message. Preserve its line order and punctuation, then
recompute the table digest from the exact text between the fence lines. A
deployment receipt never authorizes teardown, and the teardown receipt remains
separate even when a deployment used `fast-dev`.

For a read-only preflight row, use `sha256:<64 lowercase hex>` for Artifact
digest; `ACCOUNT: <value>; REGION: <value>; ENVIRONMENT: <value>`; `RESOURCES:
<comma-separated exact list>; OPERATIONS: <comma-separated exact read-only
list>`; and `COST: <explicit expected read-only billing effect>; BOUNDED_BY:
<exact approved cost posture or explicit monetary ceiling>; VALID_UNTIL: <exact
receipt Valid until value>`. Read-only does not imply zero cost. The receipt
must prohibit all mutation and must match the observed preflight before the
result becomes `READY`.

Replace every placeholder in the read-only block only after receiving that
complete owner message. Preserve its line order and punctuation, then recompute
the table digest from the exact text between the fence lines.

<!-- bootstrap:aws-read-preflight-receipt:start -->
```text
AUTHORIZE AWS READ-ONLY PREFLIGHT
Read authorization: AWS-READ-AUTH-0001
Construction authorization: AUTH-0001
Profile or role: <allowlisted profile or role>
Account: <12-digit account ID or approved alias>
Region: <AWS Region>
Environment: <environment>
Stack, application, and resources: <exact boundary>
Allowed read-only operations: <exact read-only operations>
Artifact digest: <immutable digest>
Prohibited operations: ALL_MUTATIONS
Valid until: <ISO 8601 time or exact one-operation condition>
Approver: <name/handle>
```
<!-- bootstrap:aws-read-preflight-receipt:end -->

<!-- bootstrap:aws-deployment-receipt:start -->
```text
AUTHORIZE AWS DEPLOYMENT
AWS authorization: AWS-AUTH-0001
Construction authorization: AUTH-0001
Profile or role: <allowlisted profile or role>
Account: <12-digit account ID or approved alias>
Region: <AWS Region>
Environment: <non-production or production>
Artifact digest: <immutable digest>
IaC plan/change-set binding: TYPE: <CLOUDFORMATION_CHANGE_SET|TERRAFORM_PLAN|CONTAINER_IMAGE|OTHER>; IDENTIFIER: <exact identifier>; DIGEST: sha256:<64 lowercase hex>
Stack, application, and resources: <exact boundary>
Allowed operations: <exact create/update/delete operations>
Cost ceiling: <finite positive ISO-currency amount, for example USD: 20.00>
Rollback boundary: <exact allowed rollback or NONE>
Valid until: <ISO 8601 time or exact one-operation condition>
Approver: <name/handle>
```
<!-- bootstrap:aws-deployment-receipt:end -->

<!-- bootstrap:aws-teardown-receipt:start -->
```text
AUTHORIZE AWS TEARDOWN
Teardown authorization: TEARDOWN-AUTH-0001
Construction authorization: AUTH-0001
Profile or role: <allowlisted profile or role>
Account: <12-digit account ID or approved alias>
Region: <AWS Region>
Environment: <environment>
Stack, application, and resources to remove: <exact boundary>
Resources and data to retain: <exact list or NONE>
Allowed deletion operations: <exact operations>
Shared dependencies: <exact list or NONE>
Cost effect: <expected continuing and removed billing dimensions>
Post-teardown verification: <read-only checks>
Valid until: <ISO 8601 time or exact one-operation condition>
Approver: <name/handle>
```
<!-- bootstrap:aws-teardown-receipt:end -->

For an AWS mutation, record the authorization source and receipt digest before
execution, then link the AWS-10 or AWS-40 identity/boundary evidence. Record
`FAILED` or `BLOCKED` on any mismatch. Deployment evidence is reconciled by
AWS-30; residual and teardown evidence is reconciled read-only through AWS-40
both before a teardown decision and after every AWS-50 attempt.

## Teardown reconciliation evidence

Separate the expected removal/retention manifest from observed operation
history and live inventory. An empty inventory result proves only the named
account, Region, resource types, discovery methods, permissions, and cutoff;
record every known blind spot rather than claiming global absence.

| Evidence ID | Phase | REQ / DES / AUTH | Read authorization | Teardown authorization | Teardown receipt digest | Role or profile | Expected manifest or stack | Resources proposed to remove | Allowed deletion operations | Resources retained | Shared dependencies | Cost effect | Post-teardown verification | Stack events and terminal status | Resources removed | Snapshots and backups | Residual resources | Inventory or discovery limits | Account / Region / environment | Observed at | Durable source | Identity and boundary match | Blocker or stale reason | Status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | `NOT_STARTED` |

Each concrete row has one phase. `AWS-40` uses `RUNNING`,
`READY_FOR_TEARDOWN`, `VERIFIED_CLEAN`, `RESIDUALS_REMAIN`, `BLOCKED`, or
`STALE`. `AWS-50` uses `SUCCEEDED`, `FAILED`, `PARTIAL`, or `UNKNOWN`; every
AWS-50 attempt returns to AWS-40 for read-only reconciliation.

A pre-teardown AWS-40 row records `NONE` for both teardown fields. A current
`READY_FOR_TEARDOWN` row binds the exact REQ/DES/AUTH, current read
authorization, role, account, Region, environment, removal and retention sets,
deletion operations, shared dependencies, cost effect, and post-action checks.
It proposes a teardown boundary but grants no authority. Only the separate
exact teardown receipt can authorize AWS-50.

An AWS-50 row records only the directly observed mutation attempt. It must bind
the exact `TEARDOWN-AUTH-*` ID and SHA-256 of the current owner-authored receipt,
plus its exact scope and provenance. It does not satisfy terminal read-only
reconciliation. The later AWS-40 terminal row repeats that authorization ID and
digest and must follow exactly one matching AWS-50 attempt.

`VERIFIED_CLEAN` requires terminal operation history, complete removal and
retention reconciliation, snapshots/backups, `Residual resources = NONE`, an
explicit discovery boundary, and continuing-cost disposition.
`RESIDUALS_REMAIN` requires an exact residual list and follow-up. A
`READY_FOR_TEARDOWN` result under residual-review-only intent is presented as
an owner-visible residual outcome; it is never summarized as a clean review.
`BLOCKED` records the exact safety blocker and `STALE` records the exact basis,
identity, read-authority, teardown-digest, or evidence-cutoff mismatch in
`Blocker or stale reason`. Every other concrete row records `NONE` in that
field. Malformed IDs and partially populated placeholder rows fail closed.

## Known gaps and accepted risks

| ID | Risk or gap | Severity | Owner | Review date | Rationale and authority |
|---|---|---|---|---|---|
| TODO | TODO | TODO | TODO | TODO | TODO |

An accepted risk cannot contradict a requirement or exceed AUTH. A material
scope, security, data, cost, or preservation decision routes back to the
applicable Gate A or Gate B owner decision.

## Current release decision

- Release state: `NOT_READY`
- AWS lifecycle intent: `NONE`
- Active evidence cutoff: TODO
- Blocking or stale evidence IDs: TODO
- Pending AWS evidence IDs: TODO / `NONE`
- Accepted risks: `NONE`
- Last safe checkpoint: `NONE`
- Next evidence required: TODO

Release state is exactly one of:

- `NOT_READY`: a required task, check, risk disposition, rollback, or evidence
  item is incomplete, failed, blocked, or stale;
- `READY_TO_DEPLOY`: all required pre-deployment evidence is current for the
  immutable artifact and AWS deployment is the remaining required step;
- `RELEASE_VERIFIED`: every required local and deployed acceptance item is
  VERIFIED for the identified artifact/environment, or deployed evidence is
  explicitly not applicable.

AWS lifecycle intent is exactly `NONE`, `RESIDUAL_REVIEW`, or `TEARDOWN`.
It records the owner's requested follow-up route but grants no AWS access,
mutation, cleanup, or spending authority.
`NONE` stops after release verification. `RESIDUAL_REVIEW` requests one AWS-40
read-only review and stops with its explicit result. `TEARDOWN` requests an
AWS-40 proposal, permits AWS-50 only after the exact current teardown receipt,
and always returns to AWS-40 for terminal reconciliation. A direct plain-language
owner request for residual review or teardown may update this field through
RELEASE-10; it is not itself an AWS authorization.

Only RELEASE-10 changes release state. AWS-10 requires `READY_TO_DEPLOY`.
AWS-30 records observed deployment evidence and returns to RELEASE-10, which
sets `RELEASE_VERIFIED` only when the complete release matrix supports it.
