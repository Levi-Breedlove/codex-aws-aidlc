# {{PROJECT_NAME}} — Deployment and Operations Runbook

This document explains how to validate, deploy, verify, roll back, recover, and
tear down the project. It never grants approval or AWS authority.

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

Use only the safest operation shown above. Stop when the identity, account,
Region, environment, resources, cost, recovery plan, timing, or owner approval
does not match Fastlane's current status.

<details>
<summary>View the detailed AWS authority record</summary>

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

| Environment | Purpose | AWS account | Region | Deployment method | Owner |
|---|---|---|---|---|---|
| Local | Development | N/A | N/A | TODO | TODO |
| Development | Integration and AWS validation | TODO | {{AWS_REGION}} | TODO | TODO |
| Production | User-facing workload | TODO | {{AWS_REGION}} | TODO | TODO |

## 2. Prerequisites

- Tools and versions: TODO; AWS profile or role: TODO; required permissions: TODO
- Workload identity: TODO. Prefer short-lived, narrowly scoped credentials over persistent AWS secrets.
- Environment variables: TODO; secret locations: TODO; external services: TODO
- Expected recurring cost: TODO; expected one-time deployment cost: TODO

Never place secret values in this document.

## 3. Read-only AWS preflight

Read-only AWS preflight happens only after local readiness and the owner's exact current read authorization. It confirms identity, account, Region, environment, resources, quotas, cost exposure, drift, and reversibility without mutation.

```bash
aws sts get-caller-identity
aws configure get region
TODO
```

Record observed results in the verification record. AWS Core guidance is not
proof of an AWS account check, and every AWS change remains separately unauthorized.

## 4. Local validation

Run the project-specific local checks selected in the technical plan and record
their results in the verification record.

```bash
TODO
```

Do not continue when required local readiness checks fail.

## 5. Cost preflight

Confirm:

- planning posture `{{COST_POSTURE}}` and any exact AWS-change or billable-test ceiling;
- expected low-usage cost, scaling breakpoints, expensive resources, budget alerts, and recipients;
- teardown procedure and intended retention of data, logs, images, backups, and source repositories;
- that cost savings do not weaken identity, encryption, validation, isolation, recovery, logging, or evidence.

A ceiling limits authority; it is not a guaranteed billing stop. Keep alerts, suitable service quotas, teardown capability, and observed billing checks. See [AWS Budgets](https://docs.aws.amazon.com/cost-management/latest/userguide/budgets-managing-costs.html).

## Brownfield deployment readiness

Before changing an existing environment, compare the approved preservation
record with the repository, infrastructure configuration and state, live
inventory, ownership, consumers, drift, data, interfaces, migrations, and
rollback path using read-only evidence.

Unknown ownership, unexplained drift, unapproved replacement, or an inability to restore the observed baseline stops the operation.

## Interrupted or uncertain external action

Do not blindly repeat an interrupted deployment, migration, rollback, or cleanup. Reconfirm the boundary, inspect live state read-only, classify the prior result, and compare it with the last safe checkpoint.

Continue only when the next step is safe to repeat and remains inside current
approval. A partial or unknown result stays stopped until it is checked and the
next action is authorized.

## How Fastlane runs AWS actions

Fastlane uses one clearly attributable operation or one reviewed multi-step
script. It checks the exact target and approval before acting, records what
happened, and verifies the result separately. Deployment never authorizes teardown.

## 6. Deployment

Record the exact commit or image, infrastructure version, parameter source,
environment, operator, approval references, final plan or change-set identifier,
and immutable checksums: TODO.

Deployment commands:

```bash
TODO
```

Immediately before an AWS change, recheck the identity, artifact, plan,
resources, cost, and rollback boundary. Stop on drift or a newly destructive,
shared, public, sensitive, or higher-cost effect. Record the direct result and a
separate read-only verification.

## 7. Smoke tests

```bash
TODO
```

Verify the expected user outcome, denied unauthorized access, safe logs, emitted metrics, configured alarms, and dependency-aware health checks. Record observed evidence in `VERIFY.md`.

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

1. Confirm the environment, affected users, and recent changes.
2. Check health, errors, latency, saturation, dependencies, and safe logs.
3. Check queues, retries, failed workflows, databases, storage, and IAM denials.
4. Contain the problem without destroying evidence; roll back when containment is insufficient.
5. Record unresolved causes for follow-up.

## 10. Rollback

Roll back for a failed smoke or security check, material reliability regression, migration failure, data-corruption risk, unhealthy readiness, or cost outside the approved boundary.

Rollback commands:

```bash
TODO
```

After rollback, rerun smoke tests, confirm health and alarms, verify data consistency, record evidence, and track root-cause work.

Rollback requires current authority. If it would exceed that boundary, stop safely and request only the missing authority; preserve existing resources and data.

## 11. Backup and recovery

| Item | Value |
|---|---|
| Backup mechanism | TODO |
| Backup schedule | TODO |
| Retention | TODO |
| Maximum recovery time (RTO) | TODO |
| Maximum recoverable data loss (RPO) | TODO |
| Restore procedure | TODO |
| Last restore rehearsal | TODO |
| Restore evidence | TODO |

Restore commands or procedure:

```bash
TODO
```

## 12. Incident response

1. Name the incident owner and record time, environment, and impact.
2. Preserve relevant logs, metrics, and deployment context.
3. Contain the exposure or failure; roll back or fail over when appropriate.
4. Recover service and validate primary flows.
5. Record follow-up work and update this runbook only when the procedure changes.

## 13. Teardown and decommissioning

Default to read-only inventory. Deletion requires separate current teardown authorization covering targets, retained data, shared dependencies, cost, approver, and validity. A retain, investigate, or remove choice selects a route but grants no AWS access.

Inventory command:

```bash
TODO
```

Authorized teardown command:

```bash
TODO
```

Confirm removal or intentional retention of compute and networking; databases, backups, storage, artifacts, and registries; pipelines, logs, alarms, secrets, keys, DNS, certificates, and edge resources.

Never bypass protection, force-delete data, break a shared dependency, or change retention unless explicitly authorized. After partial failure, inspect live state before any further mutation.

## 14. Residual-resource and billing verification

Read-only residual and billing verification runs before a teardown decision and after every teardown attempt.

Resource inventory command:

```bash
TODO
```

Billing and cost command:

```bash
TODO
```

Record the expected removal/retention manifest, operation status, residual resources, intentional retention, backups, inventory scope and limits, delayed billing, follow-up owner/date, and any blocker or stale reason.

Post-teardown evidence keeps the exact approval reference so it cannot be
mistaken for the result of another destructive request.

## 15. Evidence capture

For every deployment, rollback, restore, or teardown, record the version, environment, Region, times, operator, result, evidence references, linked work, and remaining gaps.

Add each observation to the verification record rather than replacing earlier
history. Preserve the approved boundary, artifact, result, retained resources,
remaining cost, and evidence gaps; a submitted request is not proof of success.

## Authorization appendices

These technical records support an audit. They do not replace the approved
technical plan, AWS permissions, observed evidence, or the owner's separate
approval for an AWS action.

<details>
<summary>Exact AWS lane mapping and phase boundaries</summary>

## Canonical AWS lanes

| Project lane | Permitted operation | Required readiness and authorization |
|---|---|---|
| `documentation-only` | AWS documentation and repository-only planning; no authenticated AWS access | Current AUTH boundary `DOCS_ONLY` |
| `read-only` | Authenticated observation inside the named account, Region, environment, and resource scope | Current Gate B `READ_ONLY` maximum boundary plus the exact current owner-authored read-only preflight receipt; no mutation |
| `fast-dev` | Listed mutations in a non-production development target | Current Gate B `MUTATE_LISTED_RESOURCES` maximum, successful AWS-10 read-only preflight, and one exact current action-specific AWS-20 authorization |
| `explicit-gate` | Documentation or read-only work by default; one separately authorized mutation | Current Gate B `MUTATE_LISTED_RESOURCES` maximum for a planned mutation, successful AWS-10 preflight, and the current action-specific AWS-20 authorization |

Prompt modes and project lanes are separate. Mutations remain serialized;
production, destructive, IAM-broadening, public, shared, retained-data, drifted,
or over-budget work uses `explicit-gate`. Teardown always has separate authority.
Both mutation lanes require the same exact deployment receipt for every new
attempt; Gate B never grants AWS mutation authority. Historical fast-dev
`AUTH-*` / `NONE` journal rows remain reconciliation-only evidence.
The compatibility adapter names the two supported execution forms
`STRUCTURED_API` and `REVIEWED_SCRIPT`; these identifiers do not grant authority.

</details>

## Conditional AWS action receipts

These are action-specific safety messages, not routine project approvals. The
first permits named reads only, the second one matching deployment, and the
third one matching teardown. Each must match Fastlane's current approved boundary.

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

The owner's exact message remains the source. Fastlane checks its target,
identity, scope, and timing before any action and keeps the observed result in
the verification record. Detailed retry and recovery rules live in the AWS
operations procedure.
