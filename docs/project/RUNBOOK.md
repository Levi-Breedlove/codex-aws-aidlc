# {{PROJECT_NAME}} — Deployment and Operations Runbook

> `docs/project/RUNBOOK.md` owns repeatable operational procedures. Project work and live status belong in `docs/project/TASKS.md` and mirrored GitHub Issues.

This document is procedural, not authorization. Gate A and Gate B are the only
routine human gates. Local validation, AWS preflight, deployment checks, smoke
tests, rollback checks, and release checks are readiness controls inside the
current construction authorization (`AUTH`), not additional human gates.

Repository, GitHub, and AWS actions occur only when the current AUTH or a
current action-specific authorization names the target and operation. Tool or
credential availability never grants authority.

Construction starts from the Gate B-authorized local Git baseline. Every
validated wave is committed locally before pause, its commit becomes the
docs/project/TASKS.md Last known-green/checkpoint commit, and the Fastlane Engine runs against that
checkpoint. Never commit protected dirty paths or infer remote/push authority
from local Git authorization.

## Active operational boundary

Complete this card before authenticated AWS work. It mirrors the authoritative
boundary; it does not create one.

| Field | Current value |
|---|---|
| Requirements / design / construction IDs | `REQ-0001` / `DES-0001` / `AUTH-0001` |
| Project AWS lane | `documentation-only` / `read-only` / `fast-dev` / `explicit-gate` |
| AWS action authorization ID | TODO / `NONE` |
| AWS action authorization source, observed at, and receipt SHA-256 | TODO / `NONE` |
| Profile or role | TODO / `NONE` |
| Account ID or approved alias | TODO / `NONE` |
| Region and environment | {{AWS_REGION}} / TODO |
| Stack, application, and exact resources | TODO / `NONE` |
| Approved operation and artifact/change set | TODO / `NONE` |
| IaC plan/change-set binding | TODO / `NONE` |
| Planning cost posture | {{COST_POSTURE}} |
| Expected billing dimensions and exact mutation cost ceiling | TODO / `NONE` |
| Rollback boundary | TODO / `NONE` |
| Teardown authorization ID | TODO / `NONE` |
| Teardown authorization source, observed at, and receipt SHA-256 | TODO / `NONE` |
| Approver and validity window | TODO / `NONE` |
| Prohibited actions | TODO |

Missing, stale, conflicting, placeholder, or mismatched values grant no mutation
authority.

## Canonical AWS lanes

| Project lane | Permitted operation | Required readiness and authorization |
|---|---|---|
| `documentation-only` | AWS documentation and repository-only planning; no authenticated AWS access | Current AUTH boundary `DOCS_ONLY` |
| `read-only` | Authenticated observation inside the named account, Region, environment, and resource scope | Current Gate B `READ_ONLY` maximum boundary plus the exact current owner-authored read-only preflight receipt; no mutation |
| `fast-dev` | Listed mutations in a non-production development target | Current Gate B `MUTATE_LISTED_RESOURCES` envelope plus successful AWS-10 read-only preflight and an exact final match |
| `explicit-gate` | Documentation or read-only work by default; one separately authorized mutation | Current Gate B `MUTATE_LISTED_RESOURCES` maximum for a planned mutation, successful AWS-10 preflight, and the current action-specific AWS-20 authorization |

`NONE`, `DOCS_ONLY`, `READ_ONLY`, and `MUTATION` are prompt access modes; they
are not interchangeable with project lane names. Every AWS mutation is
serialized, even when local task paths are disjoint. Exactly one named operator
may mutate a stack, state backend, database, or account target at a time.

For `fast-dev`, stop and route the proposed action to `explicit-gate` when the
target is production, the change deletes or replaces a resource, broadens IAM
or trust, exposes sensitive data publicly, affects a shared or unowned resource,
mutates or migrates retained data, exceeds cost, or differs from the approved
identity, Region, environment, artifact, change set, or resource list.

Deployment or rollback authority never implies teardown authority. Teardown
always requires its own exact deletion and retention authorization.

## Conditional AWS action receipts

These are action-specific safety authorizations, not routine lifecycle gates.
Authenticated AWS-10 preflight needs the exact first receipt. It permits only
the named reads and grants no mutation. An `explicit-gate` deployment needs the
exact second receipt. A `fast-dev` deployment may instead use the current Gate
B envelope only when AWS-10 records an observed current preflight and proves
the final operation is fully contained in it. Every teardown needs the exact
third receipt, including under `fast-dev`.

For every authenticated lane, Gate B's `AWS allowed operations` is the
deduplicated maximum union of exact operations needed across applicable
AWS-10, AWS-20, AWS-30, AWS-40, and AWS-50 phases. Execution uses only the
intersection of that maximum, the current phase mode, current evidence, and
current phase-specific authority. Neither the union nor an action receipt may
broaden Gate B.

Accept a receipt only when the owner's message equals the applicable complete
block after trimming surrounding whitespace. Replace every placeholder; reject
extra, missing, duplicate, reordered, commented, or fenced lines and any value
that differs from the current PRD, artifact, AWS-10/AWS-40 observation, or
caller identity.

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

The owner's exact message remains the authorization source. Before
authenticated read-only account access or mutation, copy it verbatim into the
matching uniquely marked read-preflight, deployment, or teardown receipt block
in docs/project/VERIFY.md and the protected external-operation journal named by
the construction envelope. Recompute SHA-256 from the exact normalized marked
receipt; do not copy or self-assert a digest. Record the same `Role or profile`,
`Approver`, stable source, observed ISO 8601 time, and recomputed digest in
docs/project/VERIFY.md's action-authorization evidence table. The copy and
mirror do not create or widen authority. A missing durable source, mismatched
role/profile or approver, or non-resolving receipt blocks the affected action.

A projected deployment authorization is bound to exactly one unused
`AWS-DEPLOY-nnnn` Attempt ID when its STARTED row is appended. It cannot be
carried into AWS-30 or replayed for another call. AWS-30 requires independently
current exact read authority. The AWS-10 read authorization may remain usable
only when its exact receipt already covers the reconciliation reads, target,
artifact, and validity; otherwise obtain a new exact read-only receipt before
account access. Never infer read authority from a deployment receipt.

## 1. Environments

| Environment | Purpose | AWS account | Region | Deployment method | Owner |
|---|---|---|---|---|---|
| Local | Development | N/A | N/A | TODO | TODO |
| Development | Integration and AWS validation | TODO | {{AWS_REGION}} | TODO | TODO |
| Production | User-facing workload | TODO | {{AWS_REGION}} | TODO | TODO |

## 2. Prerequisites

- Required tools and versions: TODO
- Required AWS profile or role: TODO
- Workload identity: Prefer narrowly scoped GitHub Actions OIDC with short-lived
  role credentials over persistent AWS secrets when GitHub-hosted automation is
  approved; otherwise name the exact approved temporary-credential method.
- Required permissions: TODO
- Required environment variables: TODO
- Required secret locations: TODO
- Required external services: TODO
- Expected recurring cost: TODO
- Expected one-time deployment cost: TODO

Never place secret values in this document.

## 3. Read-only AWS preflight

AWS-10 runs only when docs/project/VERIFY.md release state is `READY_TO_DEPLOY`.
First collect current documentation guidance without credentials or AWS account
access. Then present the exact read-only receipt. Only after the owner supplies
a current matching receipt may AWS-10 access its named account, profile or role,
Region, environment, resources, and read operations. State plainly that this is
authenticated read-only account access. Record `RUNNING`, then `READY`,
`BLOCKED`, or `STALE` in the read-only preflight evidence table. Never infer a
result from AWS Core documentation rows.

Under the exact read scope, confirm identity and Region using attributable
read-only operations such as:

```bash
aws sts get-caller-identity
aws configure get region
```

Confirm:

- intended profile or role;
- account identity;
- Region `{{AWS_REGION}}`;
- intended stack, application, cluster, or environment name;
- current resource collisions;
- service quota headroom;
- current budget and cost exposure;
- change reversibility;
- current matching REQ/DES/AUTH IDs and Gate B state;
- current lane, exact read authorization, and separate mutation authorization
  only after the observed preflight becomes ready;
- no protected brownfield ownership, drift, or preservation conflict.

Run IAM Access Analyzer `ValidatePolicy` only here, after current Gate B, as an
authenticated read-only policy-analysis call under the named scope. Record its
findings; do not treat access-analyzer availability as deployment authority.
Creating a CloudFormation change set is not a read-only preflight action: it
creates account-side state and requires exact mutation authority through
AWS-20. AWS-10 may inspect an existing change set created under valid authority,
or review a local deterministic diff/plan while creation remains pending.

Primary references: [IAM Access Analyzer policy validation](https://docs.aws.amazon.com/IAM/latest/UserGuide/access-analyzer-policy-validation.html),
[CloudFormation change sets](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-updating-stacks-changesets.html),
and [GitHub OIDC federation](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_providers_oidc.html).

Perform this stage through AWS-10. Execute deployment or corrective mutation
only through AWS-20, reconcile it through AWS-30, review residual resources
through AWS-40, and execute teardown only through AWS-50. BUILD-10, BUILD-20,
and RELEASE-10 never run AWS-changing commands directly.

AWS-20 always returns the exact Attempt ID to AWS-30. AWS-30 appends
independently authorized read-only evidence, including the exact read-receipt
SHA-256, validity boundary, and `Read authority source` in the exact form
`SOURCE: <stable owner-message source>; AUTHORIZED_AT: <ISO 8601 with timezone>;
RESOURCES: <exact canonical list>; OPERATIONS: <exact canonical list>`.
`AUTHORIZED_AT` is the `Observed at` timestamp of the matching Read-only
preflight row in Action authorization provenance, not the owner-message creation
time or the AWS-30 evidence-row observation time. Require the AWS observation
within that authorization window, exact journal-to-envelope resource equality,
and observed reads within the encoded operations. `COMPLETE` or
`BLOCKED` returns to RELEASE-10; the first `STALE` remains AWS-30 until current
read authority and evidence are restored. RELEASE-10 records the terminal
AWS-30 Evidence ID as VERIFY's Active evidence cutoff while deciding `NOT_READY`, `RELEASE_VERIFIED`,
or a separately authorized correction path. Once acknowledged, that attempt
cannot reroute. Retry requires distinct current mutation authority: a new exact
deployment receipt for explicit-gate or freshly approved construction
authorization for fast-dev, plus a new Attempt ID. Only RELEASE-10 changes
release state.


Add workload-specific read-only checks:

```bash
# TODO
```

## 4. Local validation

Use only the applicable validation path selected in the PRD's IaC and delivery
validation contract. Every observed row in `docs/project/VERIFY.md` uses
`COMMAND: <single local command>` or `API: <service>.<Operation>` and binds the
current TECH IDs and immutable artifact/plan.

```bash
# Formatting
TODO

# Linting and type checking
TODO

# Unit and integration tests
TODO

# Infrastructure validation
TODO

# Security and dependency checks
TODO
```

Do not continue when required local readiness checks fail.

## 5. Cost preflight

Confirm:

- planning posture: `{{COST_POSTURE}}`;
- exact finite positive mutation or billable-test ceiling when applicable;
- confirmation that the ceiling covers the authorization-validity period and
  does not exceed or change the currency of an owner-stated Gate A hard cap;
- expected low-usage cost, scaling breakpoints, budget alerts, and recipients;
- expensive resources;
- NAT Gateway, public IPv4, EKS, RDS, ALB, OpenSearch, provisioned capacity, and log-retention implications where applicable;
- teardown command or procedure;
- intended retention of data, logs, images, backups, and source repositories.

The objective is to minimize total expected cost and idle spend, not to consume
an available budget. Do not reduce required identity, encryption, secrets,
validation, isolation, recovery, logging, or evidence controls for savings.
Treat the ceiling as an authorization boundary, not a guaranteed AWS billing
stop. AWS Budgets and billing data are delayed, alerts may arrive after more
cost has accrued, and a threshold is not an immediate kill switch. Retain
alerts, teardown, service-side quotas where suitable, and observed billing
checks. See [AWS Budgets](https://docs.aws.amazon.com/cost-management/latest/userguide/budgets-managing-costs.html).

## Brownfield deployment readiness

Before changing an existing environment:

1. Record the repository and deployed baselines, including known failing checks.
2. Reconcile IaC, state backends, tags, live inventory, versions, and drift using
   read-only operations.
3. Identify owners and consumers of every existing or shared resource in the
   proposed change set.
4. Confirm protected interfaces, schemas, data, retention, imports, migrations,
   dirty paths, and rollback constraints from the approved preservation contract.
5. Prove that the proposed plan preserves owner or user changes and does not
   create, adopt, import, replace, detach, or delete an existing resource merely
   to make IaC converge.

Unknown ownership, unexplained drift, an unapproved import/replacement, or an
inability to restore the observed baseline stops the affected operation.

## Interrupted or uncertain external action

Never resume by blindly rerunning a deployment, migration, rollback, or cleanup
command. At the next checkpoint:

1. Reconfirm the exact identity, account, Region, environment, authorization,
   artifact, and expected resource boundary.
2. Inspect live state read-only and correlate operation, stack, deployment, or
   request identifiers.
3. Classify the prior action as `SUCCEEDED`, `FAILED`, `PARTIAL`, or `UNKNOWN`.
4. Compare observed resources, data, telemetry, billing dimensions, and locks to
   the last safe checkpoint.
5. Continue only when the documented next operation is idempotent, inside the
   current authorization, and safe for the observed state.

`PARTIAL` or `UNKNOWN` state is a mandatory stop unless the current authorization
explicitly covers the reconciled corrective or rollback action.

## AWS execution lanes

AWS Core selects a currently supported account-operation tool. Fastlane maps
its observable request shape into an execution lane; a tool name is neither a
product dependency nor authority.

Use `STRUCTURED_API` for one attributable operation whose service, operation,
parameters, Region/profile when exposed, and target resource can be compared
with the Engine's current `external_authority.request_match` object. Missing or
ambiguous observable fields stop mutation.

Use `REVIEWED_SCRIPT` only for a legitimate multi-step, cross-service,
paginated, retrying, parallel, conditional, or verification workflow. Before
execution, record one current `AWS-EXEC-*` row in `VERIFY.md` that binds the
exact authority and either the exact script SHA-256 or an immutable reviewed
artifact SHA-256. Hash observable script bytes at execution and compare them;
for an artifact, verify the contained regular file and its digest. An opaque or
unbound script is not exact Fastlane verification and cannot mutate or tear
down AWS resources.

Poll a long-running AWS task only when its exact task identifier is bound in
the current derived authority. A presigned URL must bind its S3 object,
upload/download operation, positive expiration, and observable profile to that
authority. Tool availability grants nothing.

Both lanes remain subject to normal Codex owner approval, IAM, the exact
deployment or teardown boundary, and AWS-30/AWS-40 evidence reconciliation.
An execution contract grants no authority, and deployment authority never
authorizes teardown.

## 6. Deployment

Record the exact reviewed artifact:

- commit:
- image digest:
- IaC version:
- parameter source:
- environment:
- operator or workflow identity:
- construction and AWS action authorization IDs:
- final read-only plan or change-set identifier:
- exact artifact and plan/change-set digests:

Deployment commands:

```bash
TODO
```

Use the canonical `AWS deployment action and reconciliation evidence` table in
`docs/project/VERIFY.md`. Every row for an Attempt ID preserves immutable
deployment authorization, receipt digest, valid-until value, and stable source.
Explicit-gate derives these from its current deployment receipt; fast-dev uses
the exact current construction `AUTH-*`, digest `NONE`, the expiry timestamp
parsed from Gate B `AWS authorization validity`, and Gate B owner-authorization
source. AWS-20 records exact `NONE` in
all read-authority provenance fields. AWS-30 records the exact read receipt
digest, validity, and four-field Read authority source envelope defined above.
A current terminal row must match the current marked read receipt and envelope;
an acknowledged historical row derives authorized resources and operations only
from its stored envelope after receipt replacement. COMPLETE acceptance IDs
each resolve exactly once in the `Verification matrix` to a `VERIFIED` row with
a concrete Requirement or invariant, concrete AWS/manual evidence, and
Artifact/environment exactly
`ARTIFACT: sha256:<64 lowercase>; ACCOUNT: <exact>; REGION: <exact>; ENVIRONMENT: <exact>`.
Acknowledged history remains auditable from stored deployment and read
provenance after either marked receipt is replaced. Before any external mutation
call, append an AWS-20 STARTED row with the unused Attempt ID and exact authorized boundary.
STARTED is a pre-call journal and is not proof that AWS received or executed
anything. Immediately after the call resolves or becomes ambiguous, append one
terminal row for the same Attempt ID with `SUCCEEDED`, `FAILED`, `PARTIAL`, or
`UNKNOWN`. Copy immutable deployment provenance and write the operation field
exactly as `IDENTIFIERS: <unique exact list or NONE — concrete reason>; RESULT: <concrete direct result>`.
Record rollback result, time, and durable source. This grammar structures
observed evidence but never proves execution by itself. Preserve both rows.

Every terminal result routes to AWS-30. A FAILED, PARTIAL, or UNKNOWN attempt
cannot be retried until AWS-30 has performed separately authorized read-only
reconciliation and RELEASE-10 has decided the next bounded action. A lingering
STARTED row is Codex-owned: with owner action NONE, append UNKNOWN, rerun the
Engine, and only then request AWS-30 read authority. Never rerun the mutation to
learn what happened. Mutation authority is one-attempt-only and cannot be replayed.
AWS-30 may append one first STALE reconciliation, followed by one later COMPLETE
or BLOCKED under a different current read authorization. Do not append a second
STALE or any row after COMPLETE or BLOCKED; repeated staleness requires human
safety review.

If the attempt STARTED while its recorded mutation authority was current but
Gate B expires or becomes legitimately stale before closure, do not reapprove
or replay the deployment merely to reconcile it. The Engine must keep standard
construction and write authority invalid and AWS mutation authority NONE. Use
only its separate `deployment_journal_closure_authority`, whose allowed path is
`docs/project/VERIFY.md` and whose bounded operation is exactly one of: append
UNKNOWN for a lone STARTED row; record the canonical marked read
receipt/provenance and append its AWS-30 journal row; or update the terminal
AWS-30 Evidence ID as RELEASE-10's Active evidence cutoff. Only deployment
journal rows are append-only. The fresh read receipt binds the immutable
historical attempt boundary and
authorizes only its listed reads; it does not renew Gate B. If STARTED occurred
after expiry, or any receipt, timing, identity, scope, row, or evidence binding
is malformed, stop for the reported safety action rather than using closure.

Immediately before mutation, recheck caller identity and prove that the final
plan is fully contained in the active boundary. Stop on any mismatch, unexpected
replacement, deletion, IAM/network exposure, shared-resource effect, retained
data impact, cost increase, alarm, or rollback trigger. Do not improvise broader
permissions or resources.

For CloudFormation, list `CreateChangeSet` and `ExecuteChangeSet` as separate
allowed operations. Creation is itself a mutation; execution is allowed only
when the reviewed identifier and canonical plan digest still match the exact
receipt. For Terraform, bind the saved plan digest to the reviewed configuration,
lockfile, variables, state/refresh mode, account, Region, and environment. For
container delivery, bind the immutable image digest and selected dependency,
SBOM, and image-validation evidence. Prefer an approved GitHub OIDC role with
short-lived credentials to persistent GitHub AWS secrets.

Checkpoint before the first mutation and after each bounded external action.
Record actual identifiers and results in `docs/project/VERIFY.md`; a submitted request is not
evidence of completion.

## 7. Smoke tests

```bash
# Health
TODO

# Primary flow
TODO

# Authentication and authorization
TODO

# Data persistence
TODO

# External integrations
TODO
```

Verify:

- expected response and user outcome;
- safe negative authorization behavior;
- logs contain no prohibited values;
- metrics are emitted;
- alarms are configured;
- health and readiness checks reflect actual dependency health.

Record evidence in `docs/project/VERIFY.md`.

## 8. Monitoring and alarms

| Signal | Source | Expected behavior | Threshold | Response |
|---|---|---|---|---|
| Availability | TODO | TODO | TODO | TODO |
| Errors | TODO | TODO | TODO | TODO |
| Latency | TODO | TODO | TODO | TODO |
| Queue or event backlog | TODO | TODO | TODO | TODO |
| Database health | TODO | TODO | TODO | TODO |
| Resource utilization | TODO | TODO | TODO | TODO |
| Cost | AWS Budgets / Cost Explorer | Remain within approved ceiling | TODO | TODO |
| Security events | TODO | TODO | TODO | TODO |

## 9. Common diagnosis flow

1. Confirm environment and user impact.
2. Check recent deployments, configuration changes, and feature flags.
3. Check health, readiness, error rate, latency, saturation, and dependency signals.
4. Inspect correlation IDs and safe structured logs.
5. Check queues, dead-letter destinations, retries, and failed workflows.
6. Check database connections, capacity, locks, and storage.
7. Check IAM denial events without broadening permissions prematurely.
8. Contain the issue without destroying evidence.
9. Roll back when containment is insufficient.
10. Create follow-up GitHub issues for unresolved causes.

## 10. Rollback

Rollback triggers:

- failed smoke test;
- security-control failure;
- error or latency regression;
- migration failure;
- data corruption risk;
- unhealthy targets or failed readiness;
- cost behavior outside approved expectations.

Rollback commands:

```bash
TODO
```

After rollback:

- rerun smoke tests;
- confirm health and alarms;
- verify data consistency;
- record evidence in `docs/project/VERIFY.md`;
- create an issue for root-cause remediation.

Rollback is performed only when the active authorization names it. If rollback
would exceed that boundary, stop in the safest observable state and report the
smallest authorization needed. In brownfield environments, preserve pre-existing
resources and data rather than forcing template state.

## 11. Backup and recovery

| Item | Value |
|---|---|
| Backup mechanism | TODO |
| Backup schedule | TODO |
| Retention | TODO |
| RTO | TODO |
| RPO | TODO |
| Restore procedure | TODO |
| Last restore rehearsal | TODO |
| Restore evidence | TODO |

Restore commands or procedure:

```bash
TODO
```

## 12. Incident response

1. Assign incident owner.
2. Record start time, environment, and impact.
3. Preserve relevant logs, metrics, and deployment context.
4. Contain exposure or failure.
5. Roll back or fail over when appropriate.
6. Recover service and validate primary flows.
7. Record follow-up actions as GitHub issues.
8. Update this runbook only when the procedure itself changes.

## 13. Teardown and decommissioning

Default to a read-only inventory. Before any deletion, record an exact current
teardown authorization that names the operator/profile, account, Region,
environment, stack/resources, retained data and backups, deletion operations,
shared dependencies, cost effect, approver, and validity window. A deployment,
rollback, Gate B fast-dev, or tool authorization does not substitute for this
teardown authorization.

The optional release field `AWS lifecycle intent` selects one non-authorizing
normal route: `NONE` stops, `RESIDUAL_REVIEW` runs AWS-40 read-only, and
`TEARDOWN` requests the teardown path. When current READY or residual evidence
requires a set-level decision, present exactly RETAIN, INVESTIGATE, or REMOVE.
RETAIN stores `RETAIN` and stops with possible continuing cost; INVESTIGATE
stores `RESIDUAL_REVIEW` and needs separate read authority; REMOVE stores
`TEARDOWN`. Follow `aws_residual_disposition`, not the raw lifecycle value.
Current REMOVE plus READY may present the exact teardown receipt; REMOVE after
`RESIDUALS_REMAIN` first refreshes AWS-40. Every choice after
`RESIDUALS_REMAIN` must be strictly newer than that row. After READY, RETAIN and
INVESTIGATE must be strictly newer, while an earlier owner-provenanced TEARDOWN
may carry forward as REMOVE. New residual evidence reopens the choice. RETAIN
without current READY or residual evidence is invalid. None of these values
authorizes AWS access or mutation. AWS-50 is
reachable only from a current `READY_FOR_TEARDOWN` AWS-40 row and the exact
current teardown receipt.

Before execution, AWS-40 derives the expected removal/retention manifest from
the approved IaC, observed stack state, and retention rules. AWS-50 executes
only the exact authorized mutation operations and records their direct service
or request outcomes, including the exact `TEARDOWN-AUTH-*` ID and receipt
SHA-256. It performs no authenticated inventory or other read-only
reconciliation.

After every AWS-50 attempt—`SUCCEEDED`, `FAILED`, `PARTIAL`, or `UNKNOWN`—return
to AWS-40 under current read authority. AWS-40 reconciles the manifest against
operation history, retained resources, created or retained snapshots/backups,
live inventory, residuals, and continuing billing signals. State the discovery
limits explicitly: resource inventory can lag, omit unsupported or
cross-account/cross-Region resources, and cannot prove absence outside the
authorized search boundary.

```bash
# Dry run or inventory
TODO

# Execution only under the exact teardown authorization
TODO
```

Confirm removal or intentional retention of:

- compute and orchestration;
- load balancers and public IP resources;
- NAT Gateways and endpoints;
- databases, backups, and snapshots;
- object storage and artifacts;
- container images and registries;
- pipelines and build resources;
- logs, alarms, dashboards, and traces;
- secrets, keys, and service accounts;
- DNS, certificates, and edge distributions.

Stop rather than disabling protection, force-deleting data, emptying storage,
breaking a shared dependency, or changing retention unless that exact action is
named. Checkpoint after each bounded step. On partial failure, inspect live state
and recompute the safe deletion order before any further mutation.

## 14. Residual-resource and billing verification

Before a teardown decision and after every AWS-50 attempt, AWS-40 performs the
authenticated read-only verification:

Record `Read authority source` exactly as `SOURCE: <stable owner-message source>;
AUTHORIZED_AT: <ISO 8601 with timezone>`. `AUTHORIZED_AT` is the `Observed at`
timestamp of the matching Read-only preflight row in Action authorization
provenance. Every current row matches the read ID, role, receipt digest, and
validity, stays inside that authorization window, and does not exceed authorized
resources or operations. Exact scope equality applies only when the Engine
requires exact-scope reconciliation; other current rows may observe a subset.
STALE cannot claim fresh reads. A later receipt expiry or replacement does not
invalidate a terminal row whose complete durable tuple was proven at append
time.

```bash
# Resource inventory checks
TODO

# Billing and cost checks
TODO
```

Record:

- expected removal/retention manifest and stack/application identifier;
- stack events or equivalent operation history and terminal status;
- residual resources;
- intentional retention;
- snapshots and backups created, retained, expired, or still pending;
- inventory/discovery services, account/Region scope, cutoff, and known limits;
- expected delayed billing records;
- follow-up date;
- owner;
- an exact `Blocker or stale reason` when AWS-40 cannot complete or its evidence
  is no longer current; all non-blocked, non-stale rows use `NONE`.

Post-AWS-50 rows repeat the exact teardown authorization ID and receipt digest
so terminal evidence cannot be attributed to a different destructive request.

## 15. Evidence capture

For every deployment, rollback, restore, or teardown, record:

- version or commit;
- environment and Region;
- start and completion time;
- operator or workflow;
- result;
- relevant test, metric, log, or stack references;
- linked GitHub issue or pull request;
- remaining evidence gaps.

Deployment attempts and their AWS-30 observations use only VERIFY's canonical
append-only deployment action and reconciliation table. Record the pre-call
STARTED row before the operation, the terminal direct result afterward, and the
separately authorized read-only reconciliation row without overwriting history.

Also record the current REQ/DES/AUTH and action authorization IDs, coordinator
checkpoint, exact account/Region/environment, resource and operation boundary,
artifact and plan/change-set binding, cost ceiling/validity period, rollback,
expiry, changed resources, billable residuals, and whether the observed operation
state is `SUCCEEDED`, `FAILED`, `PARTIAL`, or `UNKNOWN`. GitHub status
or comment updates are written only when AUTH permits those exact operations;
otherwise record `PENDING_SYNC` locally.

A terminal teardown claim is valid only from AWS-40 evidence that reconciles
the expected manifest, operation history, removed and retained resources,
backups, residuals, discovery limits, and continuing cost. A post-mutation row
also binds the exact teardown authorization and receipt digest. An AWS-50
request result alone never proves clean teardown.
