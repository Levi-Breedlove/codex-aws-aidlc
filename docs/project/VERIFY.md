# {{PROJECT_NAME}} — Verification and Release Evidence

`docs/project/VERIFY.md` owns observed proof and current evidence limits. It records what is confirmed, source-verified, observed, planned, unobserved, failed, or stale; it never grants approval or authority.

<!-- FASTLANE:DOCUMENT_SUMMARY:BEGIN -->
## Current state

| Field | Current value |
|---|---|
| Release result | Not yet initialized |
| Locally observed evidence | 0 |
| Failed or stale evidence | 0 |
| Still unobserved | Local build, AWS deployment, recovery, and teardown |
| Evidence cutoff | Not yet recorded |
| AWS account work | Not authorized |
| Updated | Not yet initialized |
| Need from you | Run `init template`. |
| Next | Codex will verify prerequisites and initialize the project. |

### Important claims

| Claim | Current maturity | Evidence | Limitation |
|---|---|---|---|
| Requirements are approved | Not yet observed | None | Gate A is not approved |
| Technical design is approved | Not yet observed | None | Gate B is not approved |
| Current AWS guidance informed the plan | Not yet observed | None | Source guidance is not deployment evidence |
| Local release checks passed | Not yet observed | None | Local evidence does not prove AWS behavior |
| Application is deployed | Not authorized | None | No deployment evidence or authority |

## Go directly to

- [Current result](#current-result)
- [Passing evidence](#verification-matrix)
- [Failed or stale evidence](#failed-or-stale)
- [AWS evidence](#aws-core-evidence)
- [Release decision](#current-release-decision)
<!-- FASTLANE:DOCUMENT_SUMMARY:END -->

<!-- FASTLANE:HUMAN_VIEW:BEGIN -->
## What this record means

Fastlane keeps this explanation synchronized with the current project records.

### Evidence picture

The current release result is Not yet initialized. Fastlane has 0 locally observed evidence records and 0 failed or stale records.

### Evidence boundary

Still unobserved: Local build, AWS deployment, recovery, and teardown. AWS account work is Not authorized. Current owner action: Run `init template`. Next, Codex will verify prerequisites and initialize the project.
<!-- FASTLANE:HUMAN_VIEW:END -->

## Current result

The current evidence dashboard and important claims appear above. Failed, stale, and unobserved claims stay visible; plans and source guidance never appear as deployed proof.

## Failed or stale

The current count appears above. Every concrete failure, stale claim, and
accepted gap remains visible in [Known gaps and accepted risks](#known-gaps-and-accepted-risks).

## Current release decision

The current release is not ready. No AWS lifecycle action is selected or
authorized, and the next required evidence remains recorded below.

<details>
<summary>Exact release decision record</summary>

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

</details>

## Known gaps and accepted risks

| ID | Risk or gap | Severity | Owner | Review date | Rationale and authority |
|---|---|---|---|---|---|
| TODO | TODO | TODO | TODO | TODO | TODO |

An accepted risk cannot contradict a requirement or exceed AUTH. A material
scope, security, data, cost, or preservation decision routes back to the
applicable Gate A or Gate B owner decision.

<details>
<summary>Exact evidence scope, maturity, and recording rules</summary>

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

### Evidence levels

| Level | Meaning | Minimum attributable basis |
|---|---|---|
| `E0_PROPOSED` | Recommendation or planned control only | Current PRD or task ID |
| `E1_SOURCE_VERIFIED` | Current official source supports the material claim | Current AWS Core or authoritative source evidence ID |
| `E2_LOCALLY_VALIDATED` | Exact local code, test, policy, IaC, or package check passed | Command, artifact/revision, and evidence ID |
| `E3_AWS_READ_OBSERVED` | Authorized read-only AWS observation confirms the target state | Account/Region scope and AWS evidence ID |
| `E4_DEPLOYED_OBSERVED` | Authorized deployment and smoke evidence confirms deployed behavior | Deployment authority, artifact/plan, and evidence ID |
| `E5_RECOVERY_OBSERVED` | Rollback, restore, or teardown behavior was exercised | Recovery/teardown authority and evidence ID |

## Evidence rules

The Engine validates attribution, freshness, scope, failure preservation, and
the difference between source, local, AWS, deployment, and recovery evidence.
### No-task requirement disposition evidence

A no-task disposition requires one current Engine-valid evidence row bound to
the exact requirement and acceptance identity. Plans and stale evidence do not qualify.
</details>

<details>
<summary>Exact source, AWS preflight, IaC, task, and validation evidence records</summary>

## AWS Core evidence

This ledger proves current runtime skill discovery through official
`aws-core@agent-toolkit-for-aws`. Search must precede matching retrieval,
and each row binds the current phase and canonical IDs without credentials,
account access, raw skill instructions, transcripts, or machine state.
| Phase | Discovery ID | Basis IDs | Plugin source | Invoked plugin identity | Observed plugin version | Capability | Observation actor | Requested skill | Returned skill identifier | Documentation query | Discovered skill identifiers | Source references | Advisory Design binding | Credentials inspected | AWS account accessed | Observed at | Evidence binding | Observed status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `REQ-10` | `AWS-DISC-0001` | TODO | TODO | TODO | TODO | `search_documentation` | TODO | — | — | `AWS skills for the current requirements-feasibility question` | TODO | TODO | `NOT_APPLICABLE — requirements feasibility only; no architecture selected` | `NO` | `NO` | TODO | TODO | `NOT_STARTED` |
| `REQ-10` | `AWS-DISC-0001` | TODO | TODO | TODO | TODO | `retrieve_skill` | TODO | TODO | TODO | — | TODO | — | `NOT_APPLICABLE — requirements feasibility only; no architecture selected` | `NO` | `NO` | TODO | TODO | `NOT_STARTED` |
| `DESIGN-10` | `AWS-DISC-0002` | TODO | TODO | TODO | TODO | `search_documentation` | TODO | — | — | `AWS skills for the current design question` | TODO | TODO | TODO | `NO` | `NO` | TODO | TODO | `NOT_STARTED` |
| `DESIGN-10` | `AWS-DISC-0002` | TODO | TODO | TODO | TODO | `retrieve_skill` | TODO | TODO | TODO | — | TODO | — | TODO | `NO` | `NO` | TODO | TODO | `NOT_STARTED` |
| `AWS-10` | `AWS-DISC-0003` | TODO | TODO | TODO | TODO | `search_documentation` | TODO | — | — | `AWS skills for the current operational question` | TODO | TODO | TODO | `NO` | `NO` | TODO | TODO | `NOT_STARTED` |
| `AWS-10` | `AWS-DISC-0003` | TODO | TODO | TODO | TODO | `retrieve_skill` | TODO | TODO | TODO | — | TODO | — | TODO | `NO` | `NO` | TODO | TODO | `NOT_STARTED` |

## Read-only AWS preflight evidence

This table records separately authorized read-only account observations. It
never grants mutation authority.
| Preflight ID | Read authorization | REQ / DES / AUTH | Artifact digest | Role or profile | Account | Region | Environment | Resources | Operations observed | AWS evidence IDs | Account access | Caller identity evidence | Boundary and drift evidence | Started at | Completed at | Identity and boundary match | Result |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `AWS-PREFLIGHT-0001` | TODO | `REQ-0001 / DES-0001 / AUTH-0001` | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | `NOT_STARTED` | TODO | TODO | TODO | TODO | TODO | `NOT_STARTED` |

## IaC validation evidence

This table records only the exact local or authorized account validation
selected by the current technical plan.
| Phase | TECH IDs | Validation method | Exact command or API | Artifact / plan / change-set binding | AWS account | AWS Region | AWS environment | Result | Observed at | Durable source |
|---|---|---|---|---|---|---|---|---|---|---|
| TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | `NOT_STARTED` | TODO | TODO |

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

Each required or triggered validation check receives one attributable current
observation. Failed results remain in history.
## Property-based test evidence

| Evidence ID | Task ID | REQ / DES / AUTH | Property ID | Framework TECH ID | Framework selection | Observed exact version | Exact command | Observed run | Replay seed or exact command | Minimized counterexample | Failure class / resolution | Result | Observed at | Commit / worktree / artifact | Durable source |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| EV-0001 | TASK-0001 | REQ-0001 / DES-0001 / AUTH-0001 | PROP-001 | TECH-0007 | TODO | TODO | TODO | TODO | TODO | `NONE` | `NONE` | `NOT_STARTED` | TODO | TODO | TODO |

Each property row records one attributable run, reproducible failure evidence
when applicable, and the exact current task and design binding.
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

</details>

<details>
<summary>Exact reviewed AWS execution contracts</summary>

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

</details>

<details>
<summary>Exact owner AWS authorization provenance and receipt copies</summary>

## Action authorization provenance

This table records the exact owner message checked for authenticated AWS work.
It is evidence only: it neither grants authority nor widens Gate B. The current
role, approver, scope, validity, stable source, and recomputed receipt digest
must match the applicable exact marked receipt and the Engine projection.

| Action | Authorization ID | Construction AUTH | Role or profile | Artifact digest | IaC plan/change-set binding | Account / Region / environment | Resources and operations | Cost ceiling and validity | Rollback boundary | Stable owner-message source | Approver | Observed at | Verbatim receipt SHA-256 | Preflight evidence | Identity and boundary match | Result |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Read-only preflight | TODO | `AUTH-0001` | TODO | TODO | `NOT_APPLICABLE — read-only preflight creates no plan` | TODO | TODO | `COST: TODO; BOUNDED_BY: TODO; VALID_UNTIL: TODO` | `NOT_APPLICABLE — no mutation` | TODO | TODO | TODO (ISO 8601 with timezone) | TODO | `NONE` | TODO | `NOT_STARTED` |
| Deployment | TODO | `AUTH-0001` | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO (ISO 8601 with timezone) | TODO | TODO / `NONE` | TODO | `NOT_STARTED` |
| Teardown | TODO | `AUTH-0001` | TODO | `NOT_APPLICABLE — teardown binds the observed inventory` | `NOT_APPLICABLE — teardown uses its removal/retention manifest` | TODO | TODO | TODO | TODO | TODO | TODO | TODO (ISO 8601 with timezone) | TODO | TODO / `NONE` | TODO | `NOT_STARTED` |

Replace placeholders only from the owner's complete current message. Preserve
the exact receipt bytes below. Read-only authority permits reads only;
deployment never authorizes teardown, and any mismatch remains blocked.

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

The Engine validates receipt equality, provenance, identity, cost, validity,
and scope before the operational skill may act. AWS-30 and AWS-40 record the
separately authorized read-only reconciliation evidence.

</details>

<details>
<summary>Exact AWS deployment and teardown reconciliation records</summary>

## AWS deployment action and reconciliation evidence

This append-only table records each deployment attempt and its separately
authorized read-only reconciliation. It is evidence, never authority.

| Evidence ID | Attempt ID | Phase | REQ / DES / AUTH | Deployment authorization | Deployment receipt digest | Deployment valid until | Deployment authority source | Read authorization | Deployment role or profile | Read role or profile | Read receipt digest | Read valid until | Read authority source | Artifact digest | Plan/change-set binding | Resources | Mutation operations | Read operations observed | Account / Region / environment | Operation identifiers and direct result | Rollback result | Acceptance evidence IDs | Observed at | Durable source | Identity and boundary match | Blocker or stale reason | Status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | `NOT_STARTED` |

The Engine and explicit AWS Operations skill enforce append order, exact
authority binding, interruption closure, retry, and reconciliation.
## Teardown reconciliation evidence

This append-only table separates the planned removal and retention boundary
from observed teardown results, residual inventory, and continuing cost.
| Evidence ID | Attempt ID | Phase | REQ / DES / AUTH | Read authorization | Read role or profile | Read receipt digest | Read valid until | Read authority source | Teardown authorization | Teardown receipt digest | Role or profile | Expected manifest or stack | Resources proposed to remove | Allowed deletion operations | Resources retained | Shared dependencies | Cost effect | Post-teardown verification | Stack events and terminal status | Resources removed | Snapshots and backups | Residual resources | Inventory or discovery limits | Account / Region / environment | Observed at | Durable source | Identity and boundary match | Blocker or stale reason | Status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | `NOT_STARTED` |

The Engine and explicit AWS Operations skill enforce the read, mutation,
interruption, residual, and terminal-state contracts for these records.
</details>
