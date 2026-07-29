---
name: operate-fastlane-aws
description: Run Fastlane AWS preflight, authorized deployment, reconciliation, review, or teardown. Use only when the user explicitly invokes this skill.
---

# Operate Fastlane AWS

1. Read the root and `infrastructure/AGENTS.md`, current REQ/DES/AUTH records,
   `docs/project/TASKS.md`, `docs/project/VERIFY.md`, `docs/project/RUNBOOK.md`, and the requested AWS prompt section.
2. Run `python scripts/bootstrap_dependencies.py --root . --json` and require
   the current official AWS Core plugin identity
   `aws-core@agent-toolkit-for-aws`. Then run
   `python scripts/bootstrap_doctor.py --root . --json`. Stop unless the
   lifecycle and release state permit the requested AWS prompt.
3. At `AWS-10`, first make a fresh live `search_documentation` call through the
   official plugin to discover current relevant AWS skill identifiers for the
   operational, deployment, IAM, Region, quota, security, reliability, and cost
   question. Select the smallest relevant identifier returned by that search,
   then make the matching live `retrieve_skill` call with that exact selected
   identifier. Bind both calls to the same current `AWS-DISC-*` record and the
   affected requirement and decision basis. This discovery is documentation
   only: inspect no credentials and access no AWS account. Record in
   `docs/project/VERIFY.md` one independently attributed row for each
   capability. Each row records source
   `aws/agent-toolkit-for-aws`, identity `aws-core@agent-toolkit-for-aws`,
   observed current semantic version, observation actor
   `CODEX_LIVE_TOOL_CALL`, capability input/output, decision influenced,
   observation time, current
   immutable-artifact binding, PASS/FAIL, `Credentials inspected` = `NO`, and
   `AWS account accessed` = `NO`; the documentation row also records returned
   official AWS sources. A generic connector, unattributed row, installation
   record, cached result, prior phase receipt, or challenger prose is insufficient.
   Missing or failed evidence blocks AWS execution planning. Record the
   observed current version only as evidence metadata; do not pin it. The
   coordinator invokes AWS Core directly; an architecture challenger
   cannot replace those live calls.
4. Treat documentation access, credentials, connector access, and IAM
   permissions as capabilities only. They never authorize an AWS change.
5. Before authenticated account access, require the Engine's authoritative
   `aws_execution.progress_state` to be `AWS_READ_SCOPE_REQUIRED`, present the
   exact `AUTHORIZE AWS READ-ONLY PREFLIGHT` receipt, and end the turn. Do not
   inspect credentials or access the named AWS account until the owner's exact
   current receipt is accepted and projected as read-only authority.
6. Run `AWS-10` read-only first. Reconfirm the caller, account, role or profile,
   Region, environment, stack, resources, operations, cost, artifact, rollback,
   and expiration against the exact active record.
   For a mutation-capable Gate B envelope, its allowed-operations row contains
   the union of exact read-only preflight/reconciliation operations and exact
   later mutation or teardown operations. Use only the subset permitted in the
   current phase.
7. Confirm expected low-usage cost, billing dimensions, scaling breakpoints,
   alerts, and the exact mutation ceiling. Treat the ceiling as a maximum, not
   a spending goal, and never weaken an approved security or recovery control
   for savings.
8. Before `AWS-20`, prove the final infrastructure diff is completely contained
   in the current approved boundary and successful observed preflight. For
   `explicit-gate`, require the Engine's authoritative
   `aws_execution.progress_state` to be `WAITING_AWS_MUTATION_AUTH` plus the
   exact current `AWS_DEPLOYMENT` receipt. For `fast-dev`, require
   `AWS_PREFLIGHT_READY` plus the current bounded `FAST_DEV_GATE_B` authority;
   Gate B is only a maximum scope and never replaces observed preflight. The
   legacy readiness boolean is compatibility output only. Serialize every
   mutation and checkpoint before and after it.
9. Route deployed observation through `AWS-30`. Record only evidence actually
   observed from the named environment.
10. Require the separate exact teardown receipt for `AWS-50`; preserve retained
    data, record only the direct mutation result with the exact teardown
    authorization ID and receipt digest, and return to `AWS-40` after every
    attempt. AWS-50 performs no authenticated read-only reconciliation. AWS-40
    verifies operation history, retained data, backups, residual resources, and
    continuing billing signals under current read authority.

Stop on any identity, target, artifact, resource, operation, cost, validity, or
state mismatch. Never broaden IAM, make sensitive data public, bypass a failed
control, or claim deployment evidence without observing it.
