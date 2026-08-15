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
| Teardown is complete | Not authorized | None | No teardown evidence or authority |

## Go directly to

- [Current result](#current-result)
- [Passing evidence](#verification-matrix)
- [Failed or stale evidence](#failed-or-stale)
- [AWS evidence](#aws-core-evidence)
- [Release decision](#current-release-decision)
<!-- FASTLANE:DOCUMENT_SUMMARY:END -->

## Current result

The current evidence dashboard and important claims appear above. Failed, stale, and unobserved claims stay visible; plans and source guidance never appear as deployed proof.

## Failed or stale

The current count appears above. Every concrete failure, stale claim, and accepted gap remains visible in [Known gaps and accepted risks](#known-gaps-and-accepted-risks).

## Current release decision

The project is not ready to release until the current evidence record says otherwise. Expand the exact record when you need its IDs or evidence cutoff.

<details>
<summary>Exact release-state record</summary>

These fields bind the release decision to the current evidence without granting AWS authority.

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

Fastlane validates release state, lifecycle intent, evidence, retry, reconciliation, and staleness through the Engine and the RELEASE/AWS procedures.

</details>

## Known gaps and accepted risks

| ID | Risk or gap | Severity | Owner | Review date | Rationale and authority |
|---|---|---|---|---|---|
| TODO | TODO | TODO | TODO | TODO | TODO |

An accepted risk cannot contradict a requirement or exceed the approved boundary. A material scope, security, data, cost, or preservation decision returns to the applicable owner review.

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

These values identify which project version and environment the evidence
describes. They do not approve repository, GitHub, or AWS actions.

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

A stale result no longer proves the current project. Local work may be complete
while a required AWS check is still pending; the release remains not ready.

### Evidence levels

| Level | Meaning | Minimum attributable basis |
|---|---|---|
| `E0_PROPOSED` | Recommendation or planned control only | Current PRD or task ID |
| `E1_SOURCE_VERIFIED` | Current official source supports the material claim | Current AWS Core or authoritative source evidence ID |
| `E2_LOCALLY_VALIDATED` | Exact local code, test, policy, IaC, or package check passed | Command, artifact/revision, and evidence ID |
| `E3_AWS_READ_OBSERVED` | Authorized read-only AWS observation confirms the target state | Account/Region scope and AWS evidence ID |
| `E4_DEPLOYED_OBSERVED` | Authorized deployment and smoke evidence confirms deployed behavior | Deployment authority, artifact/plan, and evidence ID |
| `E5_RECOVERY_OBSERVED` | Rollback, restore, or teardown behavior was exercised | Recovery/teardown authority and evidence ID |

The level shows how far a claim has actually been checked. A recommendation,
local result, AWS observation, deployment, and recovery exercise remain distinct.

## Evidence rules

Evidence states what was checked, where, when, against which project version,
and with what result. Failed, partial, and stale results remain visible. Local
checks never prove AWS behavior, and no record stores credentials or secrets.

### No-task requirement disposition evidence

When an approved requirement is already satisfied or does not apply, Fastlane
records current proof and the reason instead of creating empty work. A plan,
placeholder, or stale observation is not enough.

</details>

<details>
<summary>Exact source, AWS preflight, IaC, task, and validation evidence records</summary>

## AWS Core evidence

These records show which official AWS Core guidance informed requirements,
design, or operations. Documentation discovery does not inspect credentials or
access an AWS account; authenticated account observations are recorded
separately. Raw skill content, transcripts, secrets, and machine details are
never stored here.

| Phase | Discovery ID | Basis IDs | Plugin source | Invoked plugin identity | Observed plugin version | Capability | Observation actor | Requested skill | Returned skill identifier | Documentation query | Discovered skill identifiers | Source references | Advisory Design binding | Credentials inspected | AWS account accessed | Observed at | Evidence binding | Observed status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `REQ-10` | `AWS-DISC-0001` | TODO | TODO | TODO | TODO | `search_documentation` | TODO | — | — | `AWS skills for the current requirements-feasibility question` | TODO | TODO | `NOT_APPLICABLE — requirements feasibility only; no architecture selected` | `NO` | `NO` | TODO | TODO | `NOT_STARTED` |
| `REQ-10` | `AWS-DISC-0001` | TODO | TODO | TODO | TODO | `retrieve_skill` | TODO | TODO | TODO | — | TODO | — | `NOT_APPLICABLE — requirements feasibility only; no architecture selected` | `NO` | `NO` | TODO | TODO | `NOT_STARTED` |
| `DESIGN-10` | `AWS-DISC-0002` | TODO | TODO | TODO | TODO | `search_documentation` | TODO | — | — | `AWS skills for the current design question` | TODO | TODO | TODO | `NO` | `NO` | TODO | TODO | `NOT_STARTED` |
| `DESIGN-10` | `AWS-DISC-0002` | TODO | TODO | TODO | TODO | `retrieve_skill` | TODO | TODO | TODO | — | TODO | — | TODO | `NO` | `NO` | TODO | TODO | `NOT_STARTED` |
| `AWS-10` | `AWS-DISC-0003` | TODO | TODO | TODO | TODO | `search_documentation` | TODO | — | — | `AWS skills for the current operational question` | TODO | TODO | TODO | `NO` | `NO` | TODO | TODO | `NOT_STARTED` |
| `AWS-10` | `AWS-DISC-0003` | TODO | TODO | TODO | TODO | `retrieve_skill` | TODO | TODO | TODO | — | TODO | — | TODO | `NO` | `NO` | TODO | TODO | `NOT_STARTED` |

## Read-only AWS preflight evidence

This table separates authenticated, read-only AWS observations from
documentation research. It records the exact approved boundary, what AWS
returned, and whether the identity and target matched; it never authorizes a
change.

| Preflight ID | Read authorization | REQ / DES / AUTH | Artifact digest | Role or profile | Account | Region | Environment | Resources | Operations observed | AWS evidence IDs | Account access | Caller identity evidence | Boundary and drift evidence | Started at | Completed at | Identity and boundary match | Result |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `AWS-PREFLIGHT-0001` | TODO | `REQ-0001 / DES-0001 / AUTH-0001` | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | `NOT_STARTED` | TODO | TODO | TODO | TODO | TODO | `NOT_STARTED` |

## IaC validation evidence

These records show which project-selected infrastructure checks actually ran
and which immutable artifact or plan they checked. Local validation remains
distinct from authenticated AWS evidence.

| Phase | TECH IDs | Validation method | Exact command or API | Artifact / plan / change-set binding | AWS account | AWS Region | AWS environment | Result | Observed at | Durable source |
|---|---|---|---|---|---|---|---|---|---|---|
| TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | `NOT_STARTED` | TODO | TODO |

## Task completion evidence

Each completed task points to an observed result for the exact project version
that was checked. Failed or placeholder evidence never counts as completion.

| Evidence ID | Task | Command or observation | Result | Actor | Observed at | Commit / worktree / artifact | Durable source | Status |
|---|---|---|---|---|---|---|---|---|
| EV-0001 | TODO | TODO | TODO | TODO | TODO | TODO | TODO | `NOT_STARTED` |

## Brownfield baseline and regression evidence

For an existing application, this table compares behavior before and after the
change so known problems are not mistaken for new regressions. It does not
apply to a new application.

| Evidence ID | Baseline commit/environment | Command or observation | Pre-existing result | Post-change result | Attribution and protected behavior | Status |
|---|---|---|---|---|---|---|
| EV-0201 | TODO | TODO | TODO | TODO | TODO | `NOT_STARTED` |

An uncertain difference remains unresolved rather than being mislabeled as a
known issue or a successful repair.

## Verification matrix

| Evidence ID | PRD / property IDs | Task IDs | Requirement or invariant | Automated evidence | AWS/manual evidence | Artifact/environment | Status |
|---|---|---|---|---|---|---|---|
| EV-0101 | FR-001 | TODO | Primary outcome succeeds | TODO | TODO | TODO | `NOT_STARTED` |
| EV-0102 | SEC-001, SEC-002, PROP-001 | TODO | Protected operations enforce authentication and authorization | TODO | TODO | TODO | `NOT_STARTED` |
| EV-0103 | REL-001, REL-002, PROP-002, PROP-004 | TODO | Retry and duplicate behavior is safe | TODO | TODO | TODO | `NOT_STARTED` |
| EV-0104 | TODO | TODO | Deployment is repeatable and observable | TODO | TODO | TODO | `NOT_STARTED` |
| EV-0105 | TODO | TODO | Performance target is met | TODO | TODO | TODO | `NOT_STARTED` |
| EV-0106 | TODO | TODO | Budget and cleanup controls are effective | TODO | TODO | TODO | `NOT_STARTED` |

This matrix connects important requirements and safeguards to their current
proof and limitation. It summarizes meaningful outcomes rather than every
individual test command.

## Harness execution evidence

These records show the project-selected validation checks that actually ran,
the version or environment checked, and the observed result.

| Evidence ID | Harness ID | Layer | Basis IDs | Exact command or API | Artifact / environment | Observed result | Observed at | Durable source | Status |
|---|---|---|---|---|---|---|---|---|---|
| EV-0401 | HARNESS-001 | TODO | TODO | TODO | TODO | TODO | TODO | TODO | `NOT_STARTED` |

## Property-based test evidence

Generated checks exercise important rules across many inputs or states. The
record keeps failures and replay details so a later passing run cannot hide an
earlier defect.

| Evidence ID | Task ID | REQ / DES / AUTH | Property ID | Framework TECH ID | Framework selection | Observed exact version | Exact command | Observed run | Replay seed or exact command | Minimized counterexample | Failure class / resolution | Result | Observed at | Commit / worktree / artifact | Durable source |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| EV-0001 | TASK-0001 | REQ-0001 / DES-0001 / AUTH-0001 | PROP-001 | TECH-0007 | TODO | TODO | TODO | TODO | TODO | `NONE` | `NONE` | `NOT_STARTED` | TODO | TODO | TODO |

## Construction and release readiness checks

These checks summarize whether the approved project is ready for its next
step. They do not create another owner gate or authorize an external action.

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

This record shows what local work completed, what evidence was produced, and
the safest next action when a construction run finishes or pauses.

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

Submitting an AWS request is not proof that it completed. A separate read-only
check records whether the result succeeded, failed, was partial, or remains
unknown.

</details>

<details>
<summary>Technical records for reviewed AWS operations</summary>

## Reviewed AWS execution contracts

This record identifies the exact reviewed operation or immutable multi-step
artifact, its approved boundary, and where its result will be recorded. For
technical audit, Fastlane labels these paths `STRUCTURED_API` and
`REVIEWED_SCRIPT` (`AWS-EXEC-*`). The record never grants authority.

| Execution ID | Authority kind | Authorization ID | Receipt digest | Script SHA-256 | Immutable artifact SHA-256 | Expected operations | Resources | Account | Region | Environment | Role or profile | Artifact digest | Plan binding | Cost ceiling | Rollback boundary | Valid until | Evidence destination | Status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | `NOT_STARTED` |

The populated checksum identifies the exact reviewed content. A missing,
expired, mismatched, or unbound record remains unusable.

</details>

## Action authorization provenance

Fastlane records the exact owner authorization checked for authenticated AWS work. This evidence cannot grant authority or widen the approved technical boundary.

<details>
<summary>Exact action-authorization record</summary>

This record binds each action to its owner source, scope, validity, identity, and matching receipt without exposing credentials.

| Action | Authorization ID | Construction AUTH | Role or profile | Artifact digest | IaC plan/change-set binding | Account / Region / environment | Resources and operations | Cost ceiling and validity | Rollback boundary | Stable owner-message source | Approver | Observed at | Verbatim receipt SHA-256 | Preflight evidence | Identity and boundary match | Result |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Read-only preflight | TODO | `AUTH-0001` | TODO | TODO | `NOT_APPLICABLE — read-only preflight creates no plan` | TODO | TODO | `COST: TODO; BOUNDED_BY: TODO; VALID_UNTIL: TODO` | `NOT_APPLICABLE — no mutation` | TODO | TODO | TODO (ISO 8601 with timezone) | TODO | `NONE` | TODO | `NOT_STARTED` |
| Deployment | TODO | `AUTH-0001` | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO (ISO 8601 with timezone) | TODO | TODO / `NONE` | TODO | `NOT_STARTED` |
| Teardown | TODO | `AUTH-0001` | TODO | `NOT_APPLICABLE — teardown binds the observed inventory` | `NOT_APPLICABLE — teardown uses its removal/retention manifest` | TODO | TODO | TODO | TODO | TODO | TODO | TODO (ISO 8601 with timezone) | TODO | TODO / `NONE` | TODO | `NOT_STARTED` |

Fastlane fills this record only from a complete current owner message. Read-only authority permits reads only, deployment never authorizes teardown, and any mismatch remains blocked.

</details>

### Canonical action-authorization receipt templates

Fastlane presents the matching canonical template only when that action is ready. The owner must fill every `<...>` placeholder and return the entire block. The template is not an exact or current receipt and grants no authority; only the completed owner reply, after deterministic validation against current project state, can become the exact current receipt. The templates remain separate because read-only checks, deployment, and teardown grant different authority.

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

<details>
<summary>Technical AWS attempt and verification records</summary>

## AWS deployment action and reconciliation evidence

This append-only record preserves every AWS deployment attempt and its separate
read-only verification. It is evidence, never authority; earlier observed rows
remain available for audit.

| Evidence ID | Attempt ID | Phase | REQ / DES / AUTH | Deployment authorization | Deployment receipt digest | Deployment valid until | Deployment authority source | Read authorization | Deployment role or profile | Read role or profile | Read receipt digest | Read valid until | Read authority source | Artifact digest | Plan/change-set binding | Resources | Mutation operations | Read operations observed | Account / Region / environment | Operation identifiers and direct result | Rollback result | Acceptance evidence IDs | Observed at | Durable source | Identity and boundary match | Blocker or stale reason | Status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | `NOT_STARTED` |

Fastlane records intent before an AWS change, records the direct result without
overwriting history, and then performs a separately authorized read-only check.
Failed, partial, unknown, or stale outcomes remain visible and must be resolved
before another attempt. Detailed ordering, retry, expiry, and recovery rules
live in the AWS operations skill and are enforced by the Engine.

## Teardown reconciliation evidence

Separate the expected removal/retention manifest from observed operation
history and live inventory. An empty inventory result proves only the named
account, Region, resource types, discovery methods, permissions, and cutoff;
record every known blind spot rather than claiming global absence.

| Evidence ID | Attempt ID | Phase | REQ / DES / AUTH | Read authorization | Read role or profile | Read receipt digest | Read valid until | Read authority source | Teardown authorization | Teardown receipt digest | Role or profile | Expected manifest or stack | Resources proposed to remove | Allowed deletion operations | Resources retained | Shared dependencies | Cost effect | Post-teardown verification | Stack events and terminal status | Resources removed | Snapshots and backups | Residual resources | Inventory or discovery limits | Account / Region / environment | Observed at | Durable source | Identity and boundary match | Blocker or stale reason | Status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | `NOT_STARTED` |

This record compares the approved removal and retention plan with what was
actually observed. It distinguishes readiness, the direct teardown result, and
the later read-only inventory so an empty or incomplete observation is never
reported as globally clean. Residual resources, backups, continuing cost, and
unknown outcomes stay visible until resolved. Detailed attempt ordering and
reconciliation rules live in the AWS operations skill and are enforced by the
Engine.

</details>
