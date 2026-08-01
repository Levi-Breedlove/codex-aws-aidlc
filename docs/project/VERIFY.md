# {{PROJECT_NAME}} — Verification and Release Evidence

`docs/project/VERIFY.md` records observed proof, not plans or authorization. Gate A and Gate B
remain the only routine human gates. The checks below determine construction and
release readiness inside the current approved envelope; they are not additional
human gates.

## Current result

Read the release state and evidence cutoff in [Active evidence scope](#active-evidence-scope). This file reports proof only; it never grants approval or AWS authority.

## Proven

`VERIFIED`, `E4_DEPLOYED_OBSERVED`, and `E5_RECOVERY_OBSERVED` claims appear only when their exact evidence rows and scope are current.

## Source verified

Current official-source support is recorded as `E1_SOURCE_VERIFIED`; it is guidance, not deployed proof.

## Planned

`E0_PROPOSED`, `NOT_STARTED`, and `IMPLEMENTED` describe intended or incomplete work, not observed success.

## Not yet observed

`PENDING_AWS` and `NOT_YET_OBSERVED` identify evidence that still requires a separately authorized environment or operation.

## Failed or stale

`FAILED`, `BLOCKED`, and `STALE` remain visible with their evidence and next action. They never satisfy readiness.

## Evidence appendices

The exact scope, matrices, commands, seeds, timestamps, hashes, AWS journals, and release decision follow.
## Active evidence scope

| Field | Value |
|---|---|
| Workload | {{PROJECT_NAME}} |
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
- Coordinator-owned command outputs and attributable observations are evidence
  candidates. Read-only challengers do not claim tasks or satisfy AWS evidence.
  The coordinator reconciles evidence against changed paths before recording it.
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

### No-task requirement disposition evidence

A modern approved first-release requirement may avoid a task only through a
current Verification matrix row that satisfies all of these conditions:

- the Active evidence scope exactly matches the task plan's current
  requirements revision, design revision, and construction authorization;
- `Evidence ID` is one unique monotonic `EV-nnnn` value and `Task IDs` is
  exactly `NONE`;
- `PRD / property IDs` contains exactly the requirement ID followed by its
  canonical acceptance ID;
- `Requirement or invariant` and `Artifact/environment` are concrete, and at
  least one of `Automated evidence` or `AWS/manual evidence` records the exact
  observation; and
- status `LOCAL_PASS` or `VERIFIED` means `ALREADY_SATISFIED`; status
  `NOT_APPLICABLE` is allowed only for an `OPTIONAL_FEATURE` requirement and
  means `NOT_APPLICABLE`.

A plan, placeholder, URL alone, unscoped statement, stale observation, or
task-linked evidence cannot supply a no-task disposition. These rows remain
observed evidence, not owner approval. Task-covered requirements use their task
evidence normally and do not need a duplicate no-task row.

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

Add rows for material workload risks and every no-task requirement
disposition, not every individual test. A no-task row uses the exact current
requirement/acceptance pair and `Task IDs: NONE` as defined above.

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
| AWS design grounding | Current DESIGN-10 has fresh successful official AWS Core `search_documentation` then matching `retrieve_skill` evidence | `NOT_STARTED` |
| Task graph | Dependencies validate, waivers are explicit, every modern approved requirement has one valid derived disposition, and required tasks are complete | `NOT_STARTED` |
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

Codex follows current AWS Core guidance to select a currently supported
account-operation tool. Use
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

## AWS deployment action and reconciliation evidence

This is the canonical append-only journal for AWS-20 deployment attempts and
AWS-30 read-only reconciliation. Rows are evidence, never authority. Do not
edit, replace, reorder, or delete an earlier concrete row.

| Evidence ID | Attempt ID | Phase | REQ / DES / AUTH | Deployment authorization | Deployment receipt digest | Deployment valid until | Deployment authority source | Read authorization | Deployment role or profile | Read role or profile | Read receipt digest | Read valid until | Read authority source | Artifact digest | Plan/change-set binding | Resources | Mutation operations | Read operations observed | Account / Region / environment | Operation identifiers and direct result | Rollback result | Acceptance evidence IDs | Observed at | Durable source | Identity and boundary match | Blocker or stale reason | Status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | `NOT_STARTED` |

The placeholder row is not evidence. For each unused `AWS-DEPLOY-nnnn`
Attempt ID, append rows in this order:

1. Before any external mutation call, append an `AWS-20` `STARTED` row. Bind
   the exact deployment authorization, receipt digest, valid-until value,
   stable authority source, deployment role/profile, artifact, plan, target,
   resources, mutation operations, time, and durable source. For
   `explicit-gate`, derive those provenance fields from the current marked
   deployment receipt and its recorded source. For `fast-dev`, record the exact
   current construction `AUTH-*`, receipt digest `NONE`, the exact expiry
   timestamp parsed from Gate B `AWS authorization validity`, and the Gate B
   owner-authorization source. Copy the
   deployment authorization, its three provenance fields, and deployment
   role/profile unchanged into every later row for the Attempt ID. Use
   `NONE` for read authorization, read role/profile, read receipt digest, read
   valid until, read authority source, read operations, rollback, and acceptance
   evidence. The combined Operation identifiers and direct result field is
   exactly `NOT_OBSERVED — pre-call journal only`. STARTED proves only that
   intent was journaled; it does not prove AWS received a call.
2. After the call resolves or its outcome becomes ambiguous, append one
   terminal `AWS-20` row for the same Attempt ID with `SUCCEEDED`, `FAILED`,
   `PARTIAL`, or `UNKNOWN`. Copy the immutable deployment-authority provenance
   and append the observed operation field using exactly
   `IDENTIFIERS: <unique exact list or NONE — concrete reason>; RESULT: <concrete direct result>`.
   Also record rollback result, observation time, and durable source. This
   grammar structures the observation but does not prove execution by itself.
   Never change the STARTED row. An interrupted STARTED row receives an appended
   UNKNOWN terminal row before reconciliation. This is a Codex-owned repair with
   owner action `NONE`; rerun the Engine before requesting AWS-30 read authority.
   Never replay the mutation merely to learn what happened.
3. Under independently current exact read authority, append an `AWS-30` row
   for that Attempt ID when no terminal non-STALE reconciliation exists. Copy
   the immutable deployment-authority provenance. Populate Read authorization,
   Read role or profile, the exact SHA-256 Read receipt digest, Read valid until,
   and Read authority source exactly as `SOURCE: <stable owner-message source>;
   AUTHORIZED_AT: <ISO 8601 with timezone>; RESOURCES: <exact canonical list>;
   OPERATIONS: <exact canonical list>`. `AUTHORIZED_AT` is the `Observed at`
   timestamp of the matching Read-only preflight row in Action authorization
   provenance, not the owner-message creation time or the AWS-30 evidence-row
   observation time. Require `AUTHORIZED_AT <= Observed at <= Read valid until`, journal
   Resources exactly equal the envelope Resources, and Read operations observed
   be a subset of envelope Operations. Populate objective operation history,
   rollback observation, acceptance evidence IDs, identity/boundary match, and
   the exact blocker or stale reason. The combined operation field uses the same
   non-STARTED grammar. Deployment authorization cannot supply those reads.
   A current terminal AWS-30 row must match the current marked read receipt and
   all four envelope values. COMPLETE Acceptance evidence IDs must each
   resolve exactly once in the `Verification matrix` to a `VERIFIED` row with a
   concrete Requirement or invariant, concrete AWS/manual evidence, and
   Artifact/environment exactly `ARTIFACT: sha256:<64 lowercase>; ACCOUNT: <exact>; REGION: <exact>; ENVIRONMENT: <exact>`.
   After RELEASE-10 acknowledges it, validate the historical read boundary only
   from its stored envelope; never infer allowed operations from observed reads.
   Stored deployment and read provenance keep the row auditable even when either
   marked receipt is replaced.

Authority loss after STARTED has one narrow closure path. When STARTED occurred
while its recorded mutation authority was current and the attempt remains
structurally valid, later Gate B expiry or legitimate REQ/DES/Gate B staleness
does not erase the row and does not reactivate Gate B. The Engine exposes a
separate `deployment_journal_closure_authority` with exact allowed path
`docs/project/VERIFY.md` and one route-specific bounded operation: append an
UNKNOWN terminal row; record the canonical marked read receipt/provenance and
append its AWS-30 reconciliation row; or update the RELEASE-10 Active evidence
cutoff. Only deployment journal rows are append-only; the marked receipt and
cutoff use their canonical update contracts. During this path, standard write
authority is invalid, construction authorization is `NONE`, and AWS mutation
authority is `NONE`. A fresh read receipt may cover the immutable historical
attempt's exact reconciliation boundary even though the earlier mutation
authority has expired or become stale. No closure exception applies to a
STARTED row created after expiry, a malformed or tampered attempt, invalid
evidence, or a consumed attempt presented for retry.

Every terminal AWS-20 result requires AWS-30. A FAILED, PARTIAL, or UNKNOWN
attempt cannot be retried before reconciliation and the following RELEASE-10
decision. AWS-30 uses `COMPLETE`, `BLOCKED`, or `STALE`. COMPLETE or
BLOCKED returns to RELEASE-10; STALE remains at AWS-30 until current read
authority and evidence are restored. The deployment authority binds exactly
one Attempt ID and cannot be carried over or replayed.

An Attempt ID may have one first STALE reconciliation and then exactly one
later COMPLETE or BLOCKED reconciliation under a different current read
authorization. COMPLETE or BLOCKED is the only terminal non-STALE reconciliation;
nothing follows it. Do not append a second STALE. Repeated staleness is a
safety-review blocker rather than an automatic AWS-30 loop. A COMPLETE or
BLOCKED row's Evidence ID remains pending RELEASE-10 acknowledgment until the
Current release decision stores that exact ID as Active evidence cutoff.

## Teardown reconciliation evidence

Separate the expected removal/retention manifest from observed operation
history and live inventory. An empty inventory result proves only the named
account, Region, resource types, discovery methods, permissions, and cutoff;
record every known blind spot rather than claiming global absence.

| Evidence ID | Attempt ID | Phase | REQ / DES / AUTH | Read authorization | Read role or profile | Read receipt digest | Read valid until | Read authority source | Teardown authorization | Teardown receipt digest | Role or profile | Expected manifest or stack | Resources proposed to remove | Allowed deletion operations | Resources retained | Shared dependencies | Cost effect | Post-teardown verification | Stack events and terminal status | Resources removed | Snapshots and backups | Residual resources | Inventory or discovery limits | Account / Region / environment | Observed at | Durable source | Identity and boundary match | Blocker or stale reason | Status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | `NOT_STARTED` |

Each concrete row has one phase. `AWS-40` uses `RUNNING`,
`READY_FOR_TEARDOWN`, `VERIFIED_CLEAN`, `RESIDUALS_REMAIN`, `BLOCKED`, or
`STALE`. `AWS-50` uses one `STARTED` row followed by exactly one `SUCCEEDED`,
`FAILED`, `PARTIAL`, or `UNKNOWN` terminal row. Every AWS-50 attempt returns to
AWS-40 for read-only reconciliation.

Every concrete AWS-40 row records its read authorization, read role, receipt
digest, reusable validity boundary, observed scope, and durable authority source.
`Read authority source` uses the exact form `SOURCE: <stable owner-message
source>; AUTHORIZED_AT: <ISO 8601 with timezone>`. `AUTHORIZED_AT` is the
`Observed at` timestamp of the matching Read-only preflight row in Action
authorization provenance. Current observations must fall between that time and
`Read valid until` and never exceed the receipt's resources or operations.
Exact resource/operation equality is required only when the Engine applies
exact-scope post-action reconciliation; other current rows may observe a subset.
`STALE` records a stale basis and cannot claim fresh reads. These read fields are
distinct from `Role or profile`, which is the teardown mutation role copied into
AWS-50 evidence. A post-action review must use current read authority when it is
appended; a `STALE` review may be followed once by a terminal review only under
a fresh read-receipt tuple. Later expiry or replacement does not invalidate a
terminal row whose complete durable tuple was proven at append time.

Every pre-teardown AWS-40 row records `Attempt ID = NONE` and `NONE` for both
teardown fields. The latest append-ordered standalone AWS-40 row is the current
review epoch; an older READY row never survives a newer RUNNING, STALE, or
BLOCKED row. A fresh standalone AWS-40 row may begin a new review epoch after a
closed attempt. A current `READY_FOR_TEARDOWN` row binds the exact REQ/DES/AUTH,
current read-receipt tuple, teardown role, account, Region, environment, removal
and retention sets, deletion operations, shared dependencies, cost effect, and
post-action checks. It proposes a teardown boundary but grants no authority.
Only the separate exact teardown receipt can authorize AWS-50.

Each AWS-50 operation uses a new canonical `AWS-TEARDOWN-nnnn` Attempt ID. Its
first row is `STARTED`, appended before the AWS call and immediately after the
standalone READY row it consumes. That row binds the exact
current `READY_FOR_TEARDOWN` evidence, `TEARDOWN-AUTH-*` ID, SHA-256 of the
owner-authored receipt, role, scope, retention boundary, cost effect, and
post-teardown verification. Appending `STARTED` consumes that mutation authority;
it cannot authorize a second call or another Attempt ID.

The `STARTED` row uses `NOT_OBSERVED — pre-call journal only` for both
`Stack events and terminal status` and `Inventory or discovery limits`, and
uses `NONE` for `Resources removed`, `Snapshots and backups`, and `Residual
resources`. Its durable source identifies the pre-call journal action. No
direct-result claim appears before the AWS call.

After the hook binds `STARTED`, exactly one identical structured AWS request may
run in the same session and turn. The terminal AWS-50 row immediately follows
under the same Attempt ID and records one of `SUCCEEDED`, `FAILED`, `PARTIAL`,
or `UNKNOWN`. It binds the hook-observed tool-use and response hashes, preserves
all immutable authorization and READY fields, and replaces every pre-call
sentinel with directly observed or explicitly bounded results.

If the session ends after `STARTED` and before terminal evidence is bound, no
AWS call may be replayed. Resume permits only one local `UNKNOWN` terminal row
whose exact closure source states that the result was unobserved. That row uses
`UNKNOWN — result unavailable after interrupted attempt` for both `Stack events
and terminal status` and `Inventory or discovery limits`, `NONE` for `Resources
removed` and `Snapshots and backups`, and `UNKNOWN — no post-call inventory
observed` for `Residual resources`. It preserves the STARTED authorization,
READY binding, cost, post-verification, and account/Region/environment fields.
The workflow
then proceeds to AWS-40; new mutation authority cannot be issued until the
attempt is reconciled.

The later AWS-40 row repeats the same Attempt ID, teardown authorization ID, and
teardown receipt digest. It performs read-only residual reconciliation, must
follow exactly one terminal AWS-50 row, and durably binds the read authorization
ID, role, receipt digest, account/Region/environment plus exact resource and
operation scope, stable source, authorization time, and validity boundary used
for that observation. Missing or mismatched read proof blocks reconciliation.

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
- AWS lifecycle intent source: `NONE`
- AWS lifecycle intent recorded at: `NONE`
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

AWS lifecycle intent is one atomic three-field owner record. `AWS lifecycle
intent` uses the normal exact profile `NONE`, `RESIDUAL_REVIEW`, or `TEARDOWN`.
When current `READY_FOR_TEARDOWN` or `RESIDUALS_REMAIN` evidence requires a
set-level choice, the exact profile is `RETAIN`, `RESIDUAL_REVIEW`, or
`TEARDOWN`, shown to the owner as RETAIN, INVESTIGATE, or REMOVE. `NONE`
requires both source and recorded-at to be exactly `NONE`. Every other value
requires source exactly `owner-message MSG-AWS-LIFECYCLE-nnnn` and a
timezone-aware ISO 8601 recorded-at value. Codex must not invent, infer, or
relabel that owner message. Follow `aws_residual_disposition`, not the raw value,
for residual routing. The record selects a follow-up route but grants no AWS
access, mutation, cleanup, or spending authority.

RETAIN stores `RETAIN`, stops at an explicit retained-resources result, and
does not claim the environment is clean. INVESTIGATE stores `RESIDUAL_REVIEW`
and requires separate current read authority for AWS-40. REMOVE stores
`TEARDOWN`; current READY evidence may present AWS-50's exact teardown receipt,
while a choice after `RESIDUALS_REMAIN` first returns to AWS-40 to refresh the
proposal. Every AWS-50 attempt returns to AWS-40 for terminal reconciliation.
Every choice after `RESIDUALS_REMAIN` must be strictly newer than that row.
After READY, RETAIN and INVESTIGATE must be strictly newer. An earlier
owner-provenanced `TEARDOWN` may carry forward as REMOVE. New residual
evidence reopens the choice. RETAIN without current READY or residual evidence
is invalid. No choice substitutes for read or teardown authority. A direct
plain-language owner request atomically updates all three fields through the
bounded capability. The normal record may return to `NONE` before an elective
authenticated route begins; an active residual-choice boundary does not expose
`NONE`. Legacy records are compatible
only when their effective intent is `NONE`; a legacy non-`NONE` value without
owner provenance fails closed.

Only RELEASE-10 changes release state. AWS-10 requires `READY_TO_DEPLOY`.
Before a terminal AWS-30 row, Active evidence cutoff may be `TODO` or `NONE`.
After COMPLETE or BLOCKED, RELEASE-10 stores that exact terminal AWS-30
Evidence ID as Active evidence cutoff in the same checkpoint that decides
`NOT_READY`, `RELEASE_VERIFIED`, or records a separately authorized correction
path. A matching cutoff acknowledges the attempt and prevents it from rerouting.
Retry requires distinct current mutation authority (a new exact deployment receipt for explicit-gate, or a freshly approved construction authorization for fast-dev) and a new Attempt ID. No prior deployment authority may be replayed.
