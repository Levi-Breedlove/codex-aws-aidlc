# AWS Codex Fastlane Prompt Pack

**Pack version:** 1.3.1

Fastlane turns an idea or repository into approved requirements, an AWS-informed
plan, bounded local construction, and honest verification. Owners use the first
section; Codex uses only Engine-selected route interfaces.

## Owner command guide

| What you want | What to send |
|---|---|
| Start or resume Fastlane | `init template` |
| Choose the option currently shown | `A`, `B: <requested detail>`, or `C: <requested detail>` |
| Answer the current factual question | Reply naturally; no numeric prefix is required |
| Accept the current safe recommendation | `Accept this recommendation.` only when Fastlane offers it |
| Ask what a question means | Ask naturally, for example `Can you explain this question?` |
| Correct requirements before or after Gate A | `Change the requirements: <correction>.` |
| Correct the technical plan before or after Gate B | `Change the design: <correction>.` |
| Approve Gate A or Gate B | Copy the complete current receipt Fastlane presents, replace the approver placeholder, and send only that receipt |
| Prepare an AWS account action | Ask Codex to use `$operate-fastlane-aws` for the named read-only check, deployment, review, or teardown |

Fastlane asks once for project name, preferred AWS Region, and optional budget.
Initialization requires the owner's exact canonical Region. `recommend one`
requests guidance, never selects a Region, and waits for the next confirmation.
Intake then asks one plain-language
question per turn; owners need not select AWS services or know record IDs.

Gate A approves product scope; Gate B approves the plan and bounded local build.
Neither authorizes AWS. Reads, deployment, and teardown keep separate boundaries.

## Where the machinery lives

| Responsibility | Authority |
|---|---|
| Current project facts and owner decisions | `docs/project/` canonical records |
| Coordinator and phase procedure | `AGENTS.md` and `.agents/skills/fastlane/` references |
| AWS account operation procedure | `.agents/skills/operate-fastlane-aws/SKILL.md` |
| Exact owner commands and receipt bytes | This prompt pack |
| Parsing, readiness, digests, routing, and authority | Fastlane Engine and deterministic tests |

This file is not a second lifecycle manual. Prompt IDs are Engine-selected internal
routes, never owner instructions.

## Exactly accepted Gate receipts

Fastlane fills the current IDs and values before presenting either receipt. The
owner replaces the approver placeholder and sends the complete block without a
code fence, comments, reordered fields, or extra lines.

~~~text
APPROVE REQUIREMENTS GATE A
Requirements revision: REQ-0001
Cost posture: MINIMIZE_TOTAL_COST; HARD_CAP_NOT_STATED
Accepted assumptions: ASM-... or NONE
Approver: <name/handle>
~~~

~~~text
APPROVE PRD AND CONSTRUCTION GATE B
Requirements revision: REQ-0001
Design revision: DES-0001
Construction authorization: AUTH-0001
Construction envelope SHA-256: sha256:<64-lowercase-hex>
Use the proposed construction envelope above.
Approver: <name/handle>
~~~

Only a human owner may approve a gate. A correction is not approval. Tool
access, silence, continued conversation, and assistant-authored text are never
approval.

## AWS action receipt templates

Each block is a template, not a receipt or authority. Show only the ready
action. The owner fills every `<...>` placeholder and returns the whole block.
Only Engine validation makes that reply exact and current. None broadens Gate B
or grants another action.

~~~text
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
~~~

~~~text
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
~~~

~~~text
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
~~~

The Engine validates the owner's full block. Credentials, connectors, plugins,
prose, or earlier receipts never replace the owner's exact current message.

## Owner response formats

Routine updates are rendered from current Engine state:

~~~text
FASTLANE · <DEFINE|DESIGN|DELIVER>

Status: <plain-language state>
Updated: <material change or Nothing>
Need from you: <one concrete action or Nothing>
Next: <automatic next work>
Audit: <only consequential evidence; omitted otherwise>
~~~

Gate A and Gate B add a complete Owner Decision Brief and end with the exact
current receipt. AWS operating stages use observed values in this evidence
receipt; it reports authority and results but does not create them:

~~~text
AWS AUTHORITY AND EVIDENCE RECEIPT
Prompt: <AWS-nn>
Construction authorization: <AUTH-nnnn or NONE>
AWS authorization: <AWS-AUTH-nnnn, TEARDOWN-AUTH-nnnn, or READ_ONLY scope>
Account: <12-digit account ID or approved alias>
Region: <AWS Region>
Environment: <exact environment>
Resources: <exact resource boundary>
Operations: <authorized or observed operations>
Cost ceiling: <finite positive ISO-currency amount or NOT_APPLICABLE with reason>
Rollback: <exact boundary or NONE>
Expiration: <ISO 8601 time or exact one-operation condition>
Observed results: <concise evidence with identifiers, or NOT_RUN>
AWS Core evidence: <current attributable result or NOT_APPLICABLE with reason>
Next action: <one canonical next step or STOP>
~~~

## Prompt index

| ID | Purpose | Normal next |
|---|---|---|
| BOOT-00 | Initialize or resume Fastlane | INTAKE-10 or current Engine route |
| INTAKE-10 | Ask the next grounded application question | REQ-10 or another INTAKE-10 turn |
| REQ-10 | Complete and validate requirements | INTAKE-20 |
| INTAKE-20 | Present Gate A | DESIGN-10 after approval |
| DESIGN-10 | Complete the technical plan | DESIGN-20 |
| DESIGN-20 | Present Gate B | TASK-10 after approval |
| BUG-10 | Define one current-request defect contract | Return to the Engine route |
| DIAGRAM-10 | Compile one optional approved planned architecture board | Return to the Engine route |
| TASK-10 | Prepare the approved work plan | BUILD-10 or BUILD-20 |
| BUILD-10 | Execute one approved task | BUILD-10, BUILD-20, RELEASE-10, or stop |
| BUILD-20 | Continue approved local construction | BUILD-20, RELEASE-10, or stop |
| SYNC-10 | Reconcile one authorized GitHub request | Return to the Engine route |
| RELEASE-10 | Decide current release readiness | AWS-10, AWS-40, or stop |
| AWS-10 | Perform an authorized read-only preflight | AWS-20 or stop |
| AWS-20 | Perform one authorized deployment attempt | AWS-30 |
| AWS-30 | Verify one deployment attempt read-only | RELEASE-10 or bounded correction |
| AWS-40 | Review residual resources read-only | AWS-50 or stop |
| AWS-50 | Perform one authorized teardown attempt | AWS-40 |

## Route interface contract

The Engine selects one route. The Fastlane coordinator loads only that route,
the resolved context slices, and the relevant phase skill. The fields below
bound work; detailed procedure belongs to the named skill, and deterministic
acceptance belongs to the Engine. Every route reruns the Engine after its
checkpoint and follows the resulting next action.

---

## BOOT-00 — Bootstrap Launchpad

**Purpose:** Verify prerequisites, initialize an untouched template safely, or resume an initialized project without repeating setup.

**Preconditions:** The owner sent `init template` or a clear resume request and the Engine selected BOOT-00.

**Authoritative inputs:** Setup-assistant and Engine JSON, manifest, Git state, applicable AGENTS guidance, and ephemeral official AWS Core capability evidence for fresh setup.

**Permitted writes:** Only the exact collision-free initialization or safe correction projected by the Engine; initialized projects are not regenerated.

**GitHub mode:** No GitHub writes.

**AWS mode:** Documentation-only prerequisite discovery; no credentials or AWS account access.

**Required authorization:** The owner's current `init template` request permits only prerequisite checking and collision-free local initialization; it grants no GitHub or AWS authority.

**Stop conditions:** A real owner setup action, source-integrity conflict, unsafe collision, unsupported target, or Engine safety review.

**Receipt:** One consolidated prerequisite checklist; the complete unmodified
setup-assistant welcome; or, immediately after successful initialization, one
`project-ready` handoff from the first Engine report.

**Next:** Follow the Engine route, normally INTAKE-10 for a new project.

~~~text
[BOOT-00]
Use the Fastlane coordinator and Define procedure for the current Engine report.
When ready, run `python scripts/setup_assistant.py welcome`; return its
complete stdout verbatim as the entire owner response before setup values.
Do not summarize, abridge, preface, append to, or reformat it.
Require an owner-confirmed canonical Region. `recommend one` asks for a
recommendation, not selection; wait for a new exact-Region reply. Missing or
unconfirmed values must not reach bootstrap or writes.
After initialization, render `project-ready` once before intake.
Never render it during resume.
~~~

## INTAKE-10 — Guided Intake

**Purpose:** Record known application facts and ask exactly one remaining consequential question in plain language.

**Preconditions:** Setup is complete and the Engine projects one current intake card or safe intake correction.

**Authoritative inputs:** Current PRD intake records, repository observations, the new owner message, Engine card binding, and the derived `next_question_guidance` objective. An explicitly requested `SOURCE_ASSISTED_DEFINE` preview is non-authoritative input only.

**Permitted writes:** Only a deterministically parsed current owner answer and its normalized provenance, or an Engine-projected safe correction. Source preview writes nothing.

**GitHub mode:** No GitHub writes.

**AWS mode:** Documentation only when a current feasibility fact is material; no account access.

**Required authorization:** A new owner message bound to the current card is required for an owner decision; safe Codex-owned correction needs no owner turn.

**Stop conditions:** The presented card requires a new owner turn, the reply is stale or ambiguous, or a safety conflict is present.

**Receipt:** Routine status, Answer Confirmation when newly applicable, and one current question.

**Next:** INTAKE-10, REQ-10, or the Engine-selected correction.

~~~text
[INTAKE-10]
Use the Define and owner-response procedures for the exact current intake card.
Let the presenter explain why the current consultation objective matters and
what the answer changes. Never
ask the owner to choose Fastlane's project mode, delivery profile, effective
risk, AWS lane, or a combined internal configuration.

For an explicit product brief, load `references/source-assisted-define.md`:
preview it before writing and never treat it as approval or authority.
~~~

## REQ-10 — Requirements Analysis

**Purpose:** Turn grounded owner facts into complete, testable requirements without inventing product decisions.

**Preconditions:** Required intake foundation is complete and no owner decision remains open.

**Authoritative inputs:** Current PRD facts and decisions, repository evidence, required AWS Core documentation evidence, Engine coverage projections, and the derived Codex-owned `project_configuration` actions and basis IDs.

**Permitted writes:** Current requirements, analysis, assumptions, lineage, traceability, Gate A readiness records, and synchronized internal project configuration derived from confirmed facts.

**GitHub mode:** No GitHub writes.

**AWS mode:** Documentation-only search followed by matching retrieval when a material current AWS feasibility fact affects requirements.

**Required authorization:** Current grounded owner facts and decisions; requirements analysis grants no gate, GitHub, construction, or AWS authority.

**Stop conditions:** Missing owner fact, contradictory scope, unavailable material evidence, or incomplete requirements coverage.

**Receipt:** Routine status or the Gate A Owner Decision Brief when ready.

**Next:** INTAKE-20 when ready; otherwise the Engine-selected intake or correction route.

~~~text
[REQ-10]
Use the Define procedure and deterministic Requirements 1.5 contract. Before
requirements analysis, complete any projected Codex-owned project configuration
action from its cited facts, use the derived project mode and safest current AWS
lane, synchronize the PRD and `bootstrap.yaml`, and rerun the Engine. Do not
turn that internal classification into an owner question.
~~~

## INTAKE-20 — Requirements Gate A

**Purpose:** Let the owner review and approve the complete product agreement.

**Preconditions:** Gate A brief and canonical requirements are current, complete, and source-linked.

**Authoritative inputs:** Engine-projected Gate A brief, current requirements revision, cost posture, assumptions, and exact receipt candidate.

**Permitted writes:** Nothing until the owner sends the exact current receipt; then only the validated Gate A owner record and synchronized derived state.

**GitHub mode:** No GitHub writes.

**AWS mode:** None; Gate A never authorizes AWS account access.

**Required authorization:** The complete exact current Gate A receipt from a human owner.

**Stop conditions:** Any missing brief decision, stale source, invalid receipt, non-human approver, or requirements change.

**Receipt:** Complete Gate A Owner Decision Brief followed by the exact Gate A receipt as the final block.

**Next:** DESIGN-10 only after exact approval; otherwise remain at Gate A or follow a requirements correction.

~~~text
[INTAKE-20]
Use the owner-response and authorization-receipt procedures; validate before writing.
~~~

## DESIGN-10 — Technical PRD and Construction Envelope

**Purpose:** Compare complete architectures and produce one requirements-bound technical recommendation and construction boundary.

**Preconditions:** Gate A is current and the Engine selected DESIGN-10.

**Authoritative inputs:** Approved requirements, current repository baseline, Design procedure, current AWS Core search-and-retrieve evidence, and Engine design projections.

**Permitted writes:** Current design, technology, architecture, diagrams, validation, traceability, evidence references, and proposed construction envelope in the PRD.

**GitHub mode:** No GitHub writes.

**AWS mode:** Documentation only; design does not inspect credentials or access an AWS account.

**Required authorization:** Current Gate A approval; design work grants no GitHub, construction, or AWS account authority.

**Stop conditions:** Missing material decision, incomplete alternative analysis, stale AWS evidence, invalid diagram/traceability, or unresolved owner-controlled requirement.

**Receipt:** Routine design status or the Gate B Technical Owner Brief when ready.

**Next:** DESIGN-20 when complete; otherwise continue DESIGN-10 or follow the Engine correction route.

~~~text
[DESIGN-10]
Use the Design procedure and deterministic Design contract.
~~~

## DESIGN-20 — PRD and Construction Gate B

**Purpose:** Let the owner review the complete technical recommendation and approve bounded local construction.

**Preconditions:** Gate A, design, diagrams, decision inventory, source links, and construction-envelope digest are current.

**Authoritative inputs:** Engine-projected Gate B brief, current REQ/DES/AUTH basis, canonical construction envelope, and exact receipt candidate.

**Permitted writes:** Nothing until the owner sends the exact current receipt; then only the validated Gate B owner record and synchronized derived state.

**GitHub mode:** No GitHub writes.

**AWS mode:** None; Gate B records a maximum planned AWS boundary but does not authorize account access or teardown.

**Required authorization:** The complete exact current Gate B receipt from a human owner.

**Stop conditions:** Missing decision coverage, stale design or source, digest mismatch, invalid receipt, non-human approver, or design correction.

**Receipt:** Complete Gate B Technical Owner Brief followed by the exact Gate B receipt as the final block.

**Next:** TASK-10 only after exact approval; otherwise remain at Gate B or return to DESIGN-10 for a correction.

~~~text
[DESIGN-20]
Use the owner-response and authorization-receipt procedures; validate before writing.
~~~

## BUG-10 — Active Defect Contract

**Purpose:** Define one evidence-based bounded defect without silently changing product scope.

**Preconditions:** The current owner message requests defect analysis or repair and the existing Engine route is preserved.

**Authoritative inputs:** BUGFIX record, approved requirements/design, observed behavior, repository evidence, and current construction boundary.

**Permitted writes:** Only the bounded defect record and in-scope evidence or repair records permitted by current authority.

**GitHub mode:** No GitHub writes unless a separate current owner request names the repository and operation.

**AWS mode:** None during analysis; authenticated evidence routes through the explicit AWS-operation skill.

**Required authorization:** Existing current lifecycle authority for any repair write; analysis alone grants no write or external authority.

**Stop conditions:** Unconfirmed behavior, owner-controlled scope change, architecture impact, missing repair authority, or unsafe evidence conflict.

**Receipt:** Routine status that states whether project state changed and restores the Engine route.

**Next:** Return to the Engine-selected lifecycle route.

~~~text
[BUG-10]
Use the Deliver bugfix procedure and preserve the existing route and authority.
~~~
## DIAGRAM-10 — Planned Board
**Purpose:** Board. **Preconditions:** Request/current Gate B/DIAGRAM-0001/DIAGRAM-0008/v1.3.1/absent model.
**Authoritative inputs:** Report/PRD. **Permitted writes:** `dist/architecture/<DES>-<semantic-sha256>/**`.
**GitHub mode:** None. **AWS mode:** NONE; do not inspect credentials.
**Required authorization:** Gate B; AWS authority NONE. **Stop conditions:** Stale/mismatch/conflict/failure.
**Receipt:** `[DIAGRAM-10]`: `architecture-board-task-manifest.json`, `architecture-source.mmd`, `PENDING_DERIVATION`; no pre-creation digest. `NEW_DERIVATION` writes/hashes/reloads schema-2 `source-model.json`. Observed: crops; reported: render/icons.
**Next:** restore the route; conflict -> DESIGN-10 without silent repair; never create a third gate.
## TASK-10 — Executable Task Plan

**Purpose:** Derive one dependency-aware local work plan from the approved requirements, design, and construction boundary.

**Preconditions:** Gate B is current and the task plan is uninitialized or stale.

**Authoritative inputs:** Current PRD, Engine task-coverage projection, Deliver procedure, and exact REQ/DES/AUTH basis.

**Permitted writes:** Canonical task records, requirement dispositions, dependencies, validation bindings, attempt limits, and initial checkpoint state in TASKS.

**GitHub mode:** No GitHub writes.

**AWS mode:** Local tasks use only NONE or DOCS_ONLY; authenticated work is never task metadata.

**Required authorization:** Current Gate B approval bound to the exact REQ/DES/AUTH construction envelope.

**Stop conditions:** Missing coverage, overlapping writes, unresolved dependency, invalid task shape, or work outside Gate B.

**Receipt:** Routine construction-plan status with current progress and next action.

**Next:** BUILD-10 or BUILD-20 from Engine task readiness.

~~~text
[TASK-10]
Use the Deliver task-generation procedure and task engine; do not hand-edit run state.
~~~

## BUILD-10 — Execute One Task

**Purpose:** Complete one dependency-ready approved local task and record its proof.

**Preconditions:** Gate B, run, checkpoint, task, attempt, write boundary, and validation commands are current.

**Authoritative inputs:** Engine report, TASKS, approved PRD, Deliver procedure, repository state, and current evidence.

**Permitted writes:** The one task write set plus coordinator-owned task, evidence, checkpoint, and project-record updates required by that task.

**GitHub mode:** No GitHub writes unless separately named and authorized.

**AWS mode:** NONE or DOCS_ONLY; checkpoint and hand off before any authenticated AWS work.

**Required authorization:** Current Gate B approval, a valid run and claim, and the task's exact write and command boundaries.

**Stop conditions:** Failed evidence, exhausted attempts, stale gate, scope drift, protected-path conflict, or missing external authority.

**Receipt:** Routine task outcome and next safe action.

**Next:** Continue approved construction, RELEASE-10, or stop from the rerun Engine.

~~~text
[BUILD-10]
Use the Deliver run, claim, validation, evidence, and checkpoint procedure.
~~~

## BUILD-20 — Autonomous Construction Run

**Purpose:** Continue serialized approved local tasks until completion or a real stop condition.

**Preconditions:** Gate B and the task plan are current, a valid run can start or resume, and at least one safe task is ready.

**Authoritative inputs:** Same authorities as BUILD-10 plus current task-wave readiness and last-known-green checkpoint.

**Permitted writes:** One claimed task at a time and the same coordinator-owned records as BUILD-10.

**GitHub mode:** No GitHub writes unless separately named and authorized.

**AWS mode:** NONE or DOCS_ONLY; only the explicit AWS-operation skill may cross an account boundary.

**Required authorization:** Current Gate B approval plus the Engine-valid run, claim, checkpoint, and task boundary.

**Stop conditions:** No ready work, failing evidence, exhausted boundary or attempts, stale state, owner decision, or missing external authority.

**Receipt:** Routine status after each reconciled wave and one final stop or completion status.

**Next:** BUILD-20, RELEASE-10, or stop from the rerun Engine.

~~~text
[BUILD-20]
Use the Deliver serialized-run procedure; Codex remains the sole writer.
~~~

## SYNC-10 — GitHub Reconciliation

**Purpose:** Reconcile one owner-requested GitHub tracking or publication-adjacent record without changing the application lifecycle.

**Preconditions:** The current owner message names the repository and operation, local state is checkpointed, and current authority permits that write.

**Authoritative inputs:** Owner request, repository identity, current task/evidence records, GitHub state, and Engine route.

**Permitted writes:** Only the named GitHub objects and their exact local mirror fields.

**GitHub mode:** The one current owner-authorized repository and operation only.

**AWS mode:** None.

**Required authorization:** A current owner message naming the repository and exact GitHub operation.

**Stop conditions:** Missing or mismatched repository, operation, authority, task identity, or external state.

**Receipt:** Routine synchronization result and restored pending owner action.

**Next:** Rerun the Engine and return to its prior route.

~~~text
[SYNC-10]
Use the Deliver GitHub adjunct procedure; retain PENDING_SYNC without authority.
~~~

## RELEASE-10 — Release Readiness and Finalization

**Purpose:** Decide what is proven, what remains unobserved, and whether the exact local release is ready for an optional AWS route.

**Preconditions:** Current tasks are terminal or explicitly blocked and required local evidence is available.

**Authoritative inputs:** Current REQ/DES/AUTH, TASKS, VERIFY, RUNBOOK, package/manifest results, and any reconciled AWS evidence.

**Permitted writes:** Current release assessment, evidence cutoff, and project-specific runbook correction supported by observed facts.

**GitHub mode:** No publication or remote write without separate exact owner authority.

**AWS mode:** None until an explicit AWS operation is selected and separately authorized.

**Required authorization:** Current Gate B for local finalization; each GitHub or AWS action retains its separate exact authority.

**Stop conditions:** Missing or stale evidence, incomplete task coverage, package failure, unresolved risk, or unobserved claim presented as proven.

**Receipt:** Routine release status with `NOT_READY`, `READY_TO_DEPLOY`, or `RELEASE_VERIFIED` in plain language.

**Next:** Stop, or explicitly hand off to `$operate-fastlane-aws` for AWS-10/AWS-40 when the Engine permits it.

~~~text
[RELEASE-10]
Use the Deliver release procedure and deterministic evidence projections.
~~~

## AWS-10 — Read-Only Deployment Preflight

**Purpose:** Use current AWS Core guidance, then observe one exact AWS account boundary without changing it.

**Preconditions:** The owner explicitly invoked `$operate-fastlane-aws`, local readiness is current, and the exact read-only receipt is accepted.

**Authoritative inputs:** Engine AWS progress state, current REQ/DES/AUTH, exact read receipt, artifact, AWS Core evidence, and named account boundary.

**Permitted writes:** AWS Core and read-only preflight evidence rows; no AWS mutation.

**GitHub mode:** No GitHub writes.

**AWS mode:** READ_ONLY for only the named identity, account, Region, environment, resources, and operations.

**Required authorization:** The complete exact current AWS read-only receipt from a human owner.

**Stop conditions:** Any identity, scope, artifact, evidence, validity, drift, cost, or reversibility mismatch.

**Receipt:** AWS authority/evidence receipt with observed read results.

**Next:** AWS-20 only when separately permitted; otherwise stop or correct the read boundary.

~~~text
[AWS-10]
Use the explicit AWS-operation skill and current Engine AWS progress state.
~~~

## AWS-20 — Authorized Deployment

**Purpose:** Journal and perform one exact authorized deployment attempt.

**Preconditions:** AWS-10 is ready, final artifact/plan matches, no prior attempt is unreconciled, and current mutation authority is exact.

**Authoritative inputs:** Engine mutation projection, current REQ/DES/AUTH, preflight evidence, reviewed operation binding, and the exact deployment receipt.

**Permitted writes:** One AWS attempt plus append-only direct-result evidence and bounded local status updates.

**GitHub mode:** No GitHub writes.

**AWS mode:** MUTATION only for the exact current operation and resources.

**Required authorization:** The complete current Engine-projected `AWS_DEPLOYMENT` authority from one exact, unconsumed deployment receipt. Gate B alone never authorizes AWS mutation.

**Stop conditions:** Any mismatch, unexpected change/cost, destructive effect, failed control, expired authority, or unreconciled prior attempt.

**Receipt:** AWS authority/evidence receipt with the direct result, including unknown when observation is incomplete.

**Next:** AWS-30 under separate read authority.

~~~text
[AWS-20]
Use the AWS-operation deployment journal procedure; never infer completion from submission.
~~~

## AWS-30 — Deployed Evidence Reconciliation

**Purpose:** Verify one deployment attempt using independent current read-only authority.

**Preconditions:** One terminal AWS-20 result exists and the exact current read receipt covers its historical target.

**Authoritative inputs:** Engine reconciliation projection, immutable attempt record, read authority, live read observations, and verification matrix.

**Permitted writes:** One append-only COMPLETE, BLOCKED, or bounded STALE reconciliation and the permitted release-evidence cutoff update.

**GitHub mode:** No GitHub writes.

**AWS mode:** READ_ONLY; deployment authority never supplies these reads.

**Required authorization:** A separate complete exact current AWS read-only receipt covering the historical deployment target.

**Stop conditions:** Missing or stale read proof, target mismatch, insufficient observation, repeated staleness, or malformed history.

**Receipt:** AWS authority/evidence receipt with only observed reconciliation results.

**Next:** RELEASE-10 after COMPLETE/BLOCKED, or the one bounded correction the Engine permits.

~~~text
[AWS-30]
Use the AWS-operation reconciliation procedure and preserve append-only history.
~~~

## AWS-40 — Residual Resource and Teardown Review

**Purpose:** Observe the complete named residual-resource set and present one retain, investigate, or remove decision when needed.

**Preconditions:** The owner explicitly invoked `$operate-fastlane-aws`, the Engine permits residual review, and current read authority covers the exact scope.

**Authoritative inputs:** Engine residual projection, current and historical authority/evidence, live inventory, retention requirements, and billing limits.

**Permitted writes:** Append-only read-only residual and billing observations plus the current set-level owner disposition when supplied.

**GitHub mode:** No GitHub writes.

**AWS mode:** READ_ONLY; lifecycle intent never authorizes account access.

**Required authorization:** A complete exact current AWS read-only receipt; any retain, investigate, or remove decision must come from the owner.

**Stop conditions:** Incomplete discovery boundary, identity mismatch, stale read authority, shared dependency, uncertain retention, or unresolved cost.

**Receipt:** AWS authority/evidence receipt and, when appropriate, one plain-language set-level decision.

**Next:** Stop, continue AWS-40 investigation, or present the separate AWS-50 teardown receipt template when current REMOVE and readiness permit it.

~~~text
[AWS-40]
Use the AWS-operation residual procedure and one complete-set disposition.
~~~

## AWS-50 — Authorized Teardown

**Purpose:** Journal and perform one exact separately authorized teardown attempt.

**Preconditions:** A current READY_FOR_TEARDOWN review, current REMOVE disposition, exact teardown receipt, and no unresolved prior attempt.

**Authoritative inputs:** Engine teardown projection, current residual review, exact receipt, retention boundary, shared dependencies, cost effect, and reviewed operation.

**Permitted writes:** One teardown attempt, append-only direct-result evidence, and no read-only reconciliation.

**GitHub mode:** No GitHub writes.

**AWS mode:** MUTATION only for the exact removal operations and resources; retained data remains protected.

**Required authorization:** The complete exact current teardown receipt from a human owner.

**Stop conditions:** Any mismatch, stale review, missing protection, shared dependency, unexpected resource, expired authority, or failed control.

**Receipt:** AWS authority/evidence receipt with the direct result, including unknown when observation is incomplete.

**Next:** AWS-40 under separate read authority after every attempt.

~~~text
[AWS-50]
Use the AWS-operation teardown journal procedure; never infer clean state from the mutation result.
~~~

## Suggested model selection

Use the current strongest available reasoning model for requirements, design,
high-risk review, and release qualification. A smaller compatible model may
handle deterministic local construction when the approved task and validation
boundary are already complete. Model choice never changes gates, authority, or
evidence requirements.
