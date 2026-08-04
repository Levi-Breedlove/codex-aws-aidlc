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

<!-- FASTLANE:HUMAN_VIEW:BEGIN -->
## What this record means

Fastlane keeps this explanation synchronized with the current project records.

### Safe operation now

The deployment state is Not deployed. The safest available operation is Local validation only.

### Operational boundary

Current AWS authority is None; teardown approval is Not authorized. Current owner action: Run `init template`. Next, Codex will verify prerequisites and initialize the project.
<!-- FASTLANE:HUMAN_VIEW:END -->

## Safety boundary

Follow the safest operation shown above. Stop whenever identity, account, Region, environment, resource scope, cost, rollback, expiry, evidence, or owner authority differs from the current Engine projection.

<details>
<summary>Exact AWS authority record</summary>

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

</details>

## 1. Environments

The first-screen status identifies the current environment and Region; expand the complete map only when preparing or auditing an operation.

<details>
<summary>Exact environment map</summary>

| Environment | Purpose | AWS account | Region | Deployment method | Owner |
|---|---|---|---|---|---|
| Local | Development | N/A | N/A | TODO | TODO |
| Development | Integration and AWS validation | TODO | {{AWS_REGION}} | TODO | TODO |
| Production | User-facing workload | TODO | {{AWS_REGION}} | TODO | TODO |

</details>

## 2. Prerequisites

Before operating, confirm the selected tools, temporary identity, permissions, secrets location, dependencies, and expected cost.

<details>
<summary>Exact operational prerequisites</summary>

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

</details>

Never place secret values in this document.

## 3. Read-only AWS preflight

The read-only AWS preflight runs only after local release readiness and the owner's exact current
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

Follow the infrastructure and delivery validation path selected in the PRD.
Record every observed result in `docs/project/VERIFY.md` with its relevant
technical decisions and immutable artifact or plan.

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

Confirm the planning posture, operation ceiling, low-usage cost, scaling breakpoints, material billing drivers, alerts, teardown, and retained data.
Minimize expected total and idle cost without weakening safety or reliability. A ceiling limits authorization; it is not an instant billing stop.

## Brownfield deployment readiness

Unknown ownership, unexplained drift, unapproved replacement, or inability to
restore the observed baseline stops the operation.

<details>
<summary>Exact brownfield preflight checks</summary>

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

</details>

## Interrupted or uncertain external action

Do not repeat the command. Stop, inspect the live state read-only, classify the
result, and continue only through the Engine's reconciled safe action. Partial
or unknown state requires current authority for any correction or rollback.

## AWS execution lanes

Fastlane uses only an attributable discrete operation or reviewed digest-bound
script. The Engine and AWS Operations skill enforce the exact boundary;
deployment never authorizes teardown.

## 6. Deployment

The deployment uses one immutable reviewed artifact and the exact current
account, Region, environment, resource, cost, and rollback boundary.

<details>
<summary>Exact deployment artifact record</summary>

- commit:
- image digest:
- IaC version:
- parameter source:
- environment:
- operator or workflow identity:
- construction and AWS action authorization IDs:
- final read-only plan or change-set identifier:
- exact artifact and plan/change-set digests:

</details>

Deployment commands:

```bash
TODO
```

Immediately before mutation, recheck the complete boundary. Stop on drift or a
new destructive, shared, public, sensitive, or higher-cost effect. A submitted
request is not proof of completion.

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

Monitoring must show availability, errors, latency, dependency health, cost,
and security conditions with one clear response for each alert.

<details>
<summary>Exact monitoring and alarm records</summary>

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

</details>

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

The approved backup, retention, recovery target, restore procedure, and latest
rehearsal evidence remain recorded together.

<details>
<summary>Exact backup and recovery record</summary>

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

</details>

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
approver, and validity. Choosing to retain, investigate, or remove a resource
selects a route but never authorizes an AWS action.

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

The residual-resource review records current read-only inventory and billing evidence before a
teardown decision and after every teardown attempt.

```bash
# Resource inventory checks
TODO

# Billing and cost checks
TODO
```

<details>
<summary>Exact residual-resource and billing evidence fields</summary>

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

</details>

## 15. Evidence capture

For every operation, VERIFY records the immutable version, environment, Region,
operator, timing, result, supporting observations, and remaining gaps. Evidence
is append-only; a request never proves success.

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

<details>
<summary>Exact conditional AWS authorization receipt copies</summary>

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

</details>
