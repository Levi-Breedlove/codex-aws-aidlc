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
   full canonical `AUTHORIZE AWS READ-ONLY PREFLIGHT` receipt template, tell the
   owner to fill every `<...>` placeholder and return the entire block, and end
   the turn. Do not inspect credentials or access the named AWS account until
   the owner's complete current receipt is validated, accepted, and projected
   as read-only authority.
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
   Select `STRUCTURED_API` only for one attributable operation whose service,
   operation, parameters, context, and resources are observable and exactly
   inside current authority. Select `REVIEWED_SCRIPT` only for legitimate
   multi-step work with one current `AWS-EXEC-*` record bound to the exact
   reviewed script or immutable artifact digest, operations, resources,
   evidence destination, and authority. A description, cached script, opaque
   command, stale record, or tool name never proves or authorizes execution.
8. Before `AWS-20`, prove the final infrastructure diff is completely contained
   in the current approved boundary and successful observed preflight. For both
   `fast-dev` and `explicit-gate`, require the Engine's authoritative
   `aws_execution.progress_state` to be `WAITING_AWS_MUTATION_AUTH` plus the
   exact current `AWS_DEPLOYMENT` receipt. Gate B is only a maximum scope and
   never authorizes an AWS mutation or replaces observed preflight. The
   legacy readiness boolean is compatibility output only. Allocate one unused
   `AWS-DEPLOY-nnnn` Attempt ID and append an AWS-20 STARTED row to VERIFY's
   canonical `AWS deployment action and reconciliation evidence` table before
   the external call. Preserve the receipt's immutable `AWS-AUTH-*`
   authorization, digest, validity, and source in all new attempt rows.
   Historical fast-dev `AUTH-*` rows with receipt digest `NONE` are
   reconciliation-only evidence and can never authorize a new AWS call.
   STARTED uses the exact pre-call sentinel
   and is not proof that AWS received or executed anything. After the call
   resolves or becomes ambiguous, append exactly one terminal AWS-20 row with
   `SUCCEEDED`, `FAILED`, `PARTIAL`, or `UNKNOWN`; use exactly
   `IDENTIFIERS: <unique exact list or NONE — concrete reason>; RESULT: <concrete direct result>`
   for its operation field and record rollback. This grammar structures
   observed evidence but never proves execution by itself. Never edit or replace
   the STARTED row. If resuming with only STARTED, keep owner action NONE,
   append UNKNOWN, rerun the Engine, and only then request AWS-30 read authority.
   The projected mutation authority is consumed by that
   Attempt ID and cannot be carried over or replayed.
   If Gate B expired or became stale after STARTED, use only the Engine's
   separate `deployment_journal_closure_authority` for that exact append. It
   permits no application, task, runbook, or ordinary construction write and
   no AWS call. Never treat an expired or stale Gate B as current authority.
9. Route every terminal attempt through `AWS-30`. Require independently
   current exact read authority; never derive reads from the deployment receipt
   or reuse mutation authority. Append an AWS-30 reconciliation row for the same
   Attempt ID using `COMPLETE`, `BLOCKED`, or `STALE` and only evidence
   actually observed from the named environment. One first STALE may be
   followed by one later COMPLETE or BLOCKED under a different current read
   authorization. Store `Read authority source` exactly as `SOURCE: <stable
   owner-message source>; AUTHORIZED_AT: <ISO 8601 with timezone>; RESOURCES:
   <exact canonical list>; OPERATIONS: <exact canonical list>`. `AUTHORIZED_AT`
   is the `Observed at` timestamp of the matching Read-only preflight row in
   Action authorization provenance, not the owner-message creation time or the
   AWS-30 evidence-row observation time. Require
   `AUTHORIZED_AT <= Observed at <= Read valid until`, journal
   Resources exactly equal the encoded resources, and observed read operations
   remain a subset of the encoded operations. A current terminal row must match
   the current receipt tuple. COMPLETE IDs resolve exactly once to current VERIFIED Verification
   matrix rows with concrete requirement/invariant and AWS/manual evidence, plus
   Artifact/environment exactly
   `ARTIFACT: sha256:<64 lowercase>; ACCOUNT: <exact>; REGION: <exact>; ENVIRONMENT: <exact>`.
   After receipt expiry or replacement, derive historical authorization only
   from that stored tuple; never infer allowed operations from observed reads.
   Do not append a repeated STALE or anything after COMPLETE or BLOCKED; repeated
   staleness is a safety-review blocker. COMPLETE or BLOCKED
   returns to RELEASE-10; the first STALE remains at AWS-30 until current
   authority and evidence are restored. RELEASE-10 records the terminal AWS-30
   Evidence ID as Active evidence cutoff so it cannot reroute. A FAILED,
   PARTIAL, or UNKNOWN attempt cannot be retried before reconciliation and that
   RELEASE-10 acknowledgment. Retry requires a new exact deployment receipt
   and a new Attempt ID in both mutation lanes; Gate B reapproval is not a
   substitute for the action-specific receipt.
   CloudFormation `CreateChangeSet` is a mutation that can create account-side
   state and must be authorized separately from `ExecuteChangeSet`. An
   authenticated IAM Access Analyzer `ValidatePolicy` call is read-only AWS-10
   work and requires the current named read scope; local or documentation-only
   checks do not substitute for either observed operation.
   A structurally valid historical attempt remains closable when its Gate B
   authority later expires or becomes legitimately stale. In that case, the
   fresh read receipt binds the immutable attempted account, Region,
   environment, artifact, resources, and read scope; it does not renew Gate B
   or authorize mutation. Perform only the exact VERIFY closure operations named
   by `deployment_journal_closure_authority`: record the canonical marked read
   receipt/provenance and append its AWS-30 row. After COMPLETE or BLOCKED, use
   the narrow projection only to update RELEASE-10's Active evidence cutoff.
   Ordinary write authority, construction authorization, and AWS mutation
   authority remain NONE throughout this closure.

10. Treat AWS lifecycle intent as a non-authorizing owner record. At a settled
    release boundary, update its value, source, and recorded-at fields
    atomically. The normal profile is exactly `NONE`, `RESIDUAL_REVIEW`, or
    `TEARDOWN`. When the Engine reports a current residual-choice boundary, the
    exact profile is `RETAIN`, `RESIDUAL_REVIEW`, or `TEARDOWN`; show those to the
    owner as RETAIN, INVESTIGATE, or REMOVE. `NONE` requires `NONE` provenance;
    every other value requires source exactly
    `owner-message MSG-AWS-LIFECYCLE-nnnn` and a timezone-aware ISO 8601 time.
    Never invent the source, treat intent as read or mutation authority, or let
    `NONE` hide a STARTED attempt, required post-action reconciliation, or a
    recorded AWS-40 safety blocker. A consumed NOT_READY deployment may enter
    AWS-40 only from this separately recorded owner intent. Before authenticated
    AWS access begins, the owner may atomically cancel the elective route by
    returning the complete record to `NONE`.
11. Follow `aws_residual_disposition`, binding one choice to the current
    `READY_FOR_TEARDOWN` or `RESIDUALS_REMAIN` evidence. RETAIN stops with
    resources intentionally retained and grants no AWS authority. INVESTIGATE
    requires separate current read authority and routes to AWS-40. REMOVE on
    current `READY_FOR_TEARDOWN` may present AWS-50's full canonical receipt
    template for owner completion; REMOVE after `RESIDUALS_REMAIN` first returns
    to AWS-40 to refresh the proposal. Every
    choice after `RESIDUALS_REMAIN` must be strictly newer than that row. After
    READY, RETAIN and INVESTIGATE must be strictly newer, while an earlier
    owner-provenanced TEARDOWN may carry forward as REMOVE. New residual evidence
    reopens the choice. Never infer mixed choices for individual resources from
    the one set-level disposition.
12. For every concrete AWS-40 row, store `Read authority source` exactly as `SOURCE:
    <stable owner-message source>; AUTHORIZED_AT: <ISO 8601 with timezone>`.
    `AUTHORIZED_AT` is the `Observed at` timestamp of the matching Read-only
    preflight row in Action authorization provenance. Require current read ID,
    role, digest, and validity at append time, with `Observed at` inside the
    authorization window. Observed resources and operations never exceed the
    receipt; exact equality applies only when the Engine requires exact-scope
    reconciliation. STALE cannot claim fresh reads. Terminal history remains
    valid after later expiry or replacement only because its durable tuple was
    proven; lifecycle intent never supplies these reads.
13. Require the separate exact teardown receipt for `AWS-50`; preserve retained
    data and consume one current `READY_FOR_TEARDOWN` review. Allocate one new
    `AWS-TEARDOWN-nnnn` Attempt ID and append its immutable `STARTED` record
    before the call; STARTED reports no observed result and consumes that
    teardown authority for exactly one matching request. Append exactly one
    `SUCCEEDED`, `FAILED`, `PARTIAL`, or `UNKNOWN` terminal row with the direct
    result and exact receipt digest. If a session ends with only STARTED, never
    replay the call; append the bounded local UNKNOWN closure the Engine permits.
    Return to `AWS-40` after every attempt. AWS-50 performs no authenticated
    read-only reconciliation. Under separate current read authority, AWS-40
    verifies operation history, retained data, backups, residual resources,
    discovery limits, and continuing billing signals. Never claim globally
    clean state from an empty or scope-limited inventory.

Stop on any identity, target, artifact, resource, operation, cost, validity, or
state mismatch. Never broaden IAM, make sensitive data public, bypass a failed
control, replay deployment authority, retry an unreconciled attempt, or claim
deployment evidence without observing it.

`docs/project/VERIFY.md` stores the canonical evidence rows and
`docs/project/RUNBOOK.md` stores project-specific operator commands and stop
conditions. Neither document owns this execution procedure. Exact receipt bytes
remain in the prompt authority; the Engine owns routing, field grammar,
matching, consumption, journal closure, and fail-closed diagnostics.
