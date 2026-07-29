# AWS Infrastructure Engineering Guide

These instructions apply under `infrastructure/` and inherit root `AGENTS.md`.
This guide narrows the root rules and never widens approval or authorization.
Gate A and Gate B are the only routine human gates.

## Plain-language summary

Inspect first. Change AWS only when the current approval names the exact
account, Region, environment, resources, operations, cost limit, rollback plan,
and expiration. Stop when the observed target or final change differs.
Credentials and tools are never permission.

Read the current REQ/DES/AUTH IDs and AWS boundary in
`../docs/project/PRD.md`, the assigned task in `../docs/project/TASKS.md`,
evidence in `../docs/project/VERIFY.md`, and deployment/recovery procedures in
`../docs/project/RUNBOOK.md`.

## Agent reference — exact infrastructure rules

- Require current Gate B `APPROVED_FOR_CONSTRUCTION`, matching REQ/DES/AUTH
  IDs, and one assigned `READY` task before claiming work.
- AUTH and the task are maximum file, command, GitHub, identity, account,
  Region, environment, resource, cost, and mutation boundaries.
- Use AWS Core and current primary AWS documentation for service, IAM, quota,
  networking, encryption, recovery, cost, and Region facts. It advises; it
  never authorizes.
- The coordinator alone writes project ledgers, lifecycle state, shared
  manifests, lockfiles, schemas, generated output, checkpoints, and GitHub
  state. The coordinator alone performs every repository and infrastructure
  edit. Helpers and challengers are read-only: they may inspect assigned
  disjoint paths and return findings or receipts, but never edit, claim tasks,
  approve, authorize, or mutate AWS.
  This restriction propagates to every descendant subagent: a read-only
  helper or challenger cannot spawn a writer, task claimant, state mutator,
  approver, authorizer, or AWS operator.
- Give every path, stack, state backend, environment, database, generated
  output, and mutable resource one writer. Serialize state operations, imports,
  migrations, deployments, rollback, and every AWS mutation.
- Checkpoint around external mutations. After interruption, inspect read-only
  and classify the last action `SUCCEEDED`, `FAILED`, `PARTIAL`, or `UNKNOWN`;
  never blindly rerun it.

| AWS lane | Allowed behavior |
|---|---|
| `documentation-only` | Repository planning and documentation lookup; no authenticated AWS access |
| `read-only` | Observe only the identity, Region, environment, and resources named by the exact current owner-authored read-only preflight receipt within Gate B's maximum boundary |
| `fast-dev` | Mutate listed non-production resources only after matching AWS-10 preflight |
| `explicit-gate` | Remain documentation-only/read-only until an exact current AWS-20 authorization |

Immediately before mutation, reconfirm profile/role, account, Region,
environment, resources, operation, artifact/change set, cost, rollback,
authorization ID, approver, and validity. Route to `explicit-gate` and stop on
production, deletion/replacement, IAM or trust broadening, public sensitive-data
exposure, shared/unowned resources, data mutation/migration, cost drift, or any
identity, artifact, target, plan, or scope mismatch. Teardown always requires a
separate exact authorization.

For brownfield work, inspect IaC, state backends, live resources, drift, owners,
consumers, interfaces, data, and baseline failures before changing anything.
Unknown ownership is not permission. Never overwrite observed state to make it
match the template; stop when drift, rollback, or a preservation boundary is
unresolved.

Use infrastructure as code, least privilege, explicit trust, private defaults,
approved encryption, logging, retention, backup, health checks, alarms,
rollback, recovery, cleanup, and cost controls. Keep secrets out of source,
state output, logs, receipts, and command history. Validate and inspect the
final plan or change set. Never weaken a control to make an operation pass, and
never claim deployed success without observed read-only evidence.
