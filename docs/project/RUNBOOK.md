# {{PROJECT_NAME}} — Deployment and Operations Runbook

`docs/project/RUNBOOK.md` owns repeatable operational procedures. It does not grant approval or AWS authority.

<!-- FASTLANE:DOCUMENT_SUMMARY:BEGIN -->
## Current state

| Field | Current value |
|---|---|
| Environment | Not yet initialized |
| Deployment state | Not deployed |
| Current AWS authority | None |
| Construction approval | Not yet initialized |
| Safest available operation | Local validation only |
| Deployment approval | Not authorized |
| Teardown approval | Not authorized |
| Recovery state | Not yet observed |
| Emergency condition | No deployed environment exists |
| AWS account work | Not authorized |
| Updated | Not yet initialized |
| Need from you | Run `init template`. |
| Next | Codex will verify prerequisites and initialize the project. |

## Go directly to

- [Before deploying](#2-prerequisites)
- [Deploy](#6-deployment)
- [Verify](#7-smoke-tests)
- [Roll back](#10-rollback)
- [Recover](#11-backup-and-recovery)
- [Tear down](#13-teardown-and-decommissioning)
<!-- FASTLANE:DOCUMENT_SUMMARY:END -->

## Safety boundary

Use only the safest operation shown above. Stop whenever identity, account, Region, environment, resource scope, cost, rollback, expiry, evidence, or owner authority differs from the current Engine projection.

## Active operational boundary

Complete this card before authenticated AWS work. It mirrors the authoritative
boundary; it does not create one.

| Field | Current value |
|---|---|
| Current project boundary | `REQ-0001` / `DES-0001` / `AUTH-0001`; lane: `documentation-only` / `read-only` / `fast-dev` / `explicit-gate` |
| Current AWS authority | Action authorization ID, source, observed time, receipt SHA-256, and approved profile or role: TODO / `NONE` |
| Region and environment | Account ID or approved alias: TODO / `NONE`; Region/environment: {{AWS_REGION}} / TODO |
| Resources and operation | Exact stack/application/resources, operation, artifact, and IaC plan/change-set binding: TODO / `NONE` |
| Cost boundary | Planning posture: {{COST_POSTURE}}; billing dimensions and exact mutation ceiling: TODO / `NONE` |
| Rollback and teardown | Rollback boundary plus separate teardown ID/source/time/digest: TODO / `NONE` |
| Human authority | Approver and validity window: TODO / `NONE` |
| Prohibited actions | TODO |

Missing, stale, conflicting, placeholder, or mismatched values grant no mutation
authority.

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

AWS-10 runs only after local release readiness and the owner's exact current
read-only receipt. It confirms the named identity, account, Region, environment,
resources, quotas, cost exposure, drift, and reversibility without mutation.

```bash
aws sts get-caller-identity
aws configure get region
# Add workload-specific read-only checks.
TODO
```

Record observed results in `VERIFY.md`. AWS Core documentation is source evidence,
not account evidence; change-set creation and every mutation remain unauthorized.

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

Fastlane uses either one attributable `STRUCTURED_API` operation or a digest-bound
`REVIEWED_SCRIPT` for legitimate multi-step work. The Engine and AWS Operations
skill validate the exact request, authority, journal, retry, and reconciliation;
tool availability grants nothing and deployment never authorizes teardown.

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

Immediately before mutation, recheck identity and prove the immutable artifact,
plan, operation, resources, cost, and rollback fit the active boundary exactly.
Stop on drift or a newly destructive, shared, public, sensitive, or higher-cost
effect. Record the pre-call checkpoint, direct result, and separate read-only
reconciliation in `VERIFY.md`; a submitted request is not proof of completion.

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

Default to read-only inventory. Deletion requires a separate exact current
teardown receipt covering the target, retained data, shared dependencies, cost,
approver, and validity. `RETAIN`, `INVESTIGATE`, and `REMOVE` choose a route but
never authorize an AWS action.

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

AWS-40 records current read-only residual and billing evidence before a teardown decision and after every teardown attempt.

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

Use VERIFY's append-only action and reconciliation tables. Record the exact
boundary, immutable artifact, result, retained resources, residual cost, and
remaining evidence gaps; never overwrite history or infer success from a request.

## Authorization appendices

The exact lane map and action receipts below remain subordinate to Gate B, action-specific owner authorization, IAM, and observed evidence.

<details>
<summary>Exact AWS lane mapping and phase boundaries</summary>

## Canonical AWS lanes

| Project lane | Permitted operation | Required readiness and authorization |
|---|---|---|
| `documentation-only` | AWS documentation and repository-only planning; no authenticated AWS access | Current AUTH boundary `DOCS_ONLY` |
| `read-only` | Authenticated observation inside the named account, Region, environment, and resource scope | Current Gate B `READ_ONLY` maximum boundary plus the exact current owner-authored read-only preflight receipt; no mutation |
| `fast-dev` | Listed mutations in a non-production development target | Current Gate B `MUTATE_LISTED_RESOURCES` envelope plus successful AWS-10 read-only preflight and an exact final match |
| `explicit-gate` | Documentation or read-only work by default; one separately authorized mutation | Current Gate B `MUTATE_LISTED_RESOURCES` maximum for a planned mutation, successful AWS-10 preflight, and the current action-specific AWS-20 authorization |

Prompt modes and project lanes are separate. Mutations remain serialized;
production, destructive, IAM-broadening, public, shared, retained-data, drifted,
or over-budget work uses `explicit-gate`. Teardown always has separate authority.

</details>

## Conditional AWS action receipts

These are action-specific safety authorizations, not routine lifecycle gates.
The first permits named reads only, the second permits one matching deployment,
and the third permits one matching teardown. Exact equality and the current
Engine projection are required; no receipt may broaden Gate B.

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

The owner's exact message remains the source. Fastlane records it verbatim in
VERIFY and the protected journal, recomputes its digest, and rejects any target,
identity, scope, timing, or provenance mismatch. The AWS Operations skill owns
the exact journal, retry, and reconciliation procedure.
