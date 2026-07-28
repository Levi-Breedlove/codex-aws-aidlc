# AWS Codex Fastlane Prompt Pack

**Pack version:** 1.0.1

This pack turns a rough idea or an existing repository into a reviewed,
executable AWS delivery plan, then lets Codex run the approved work for long
periods without turning delivery into a document factory.

The default is the **native fast lane**:

~~~text
BOOT-00
  -> INTAKE-10
  -> REQ-10
  -> INTAKE-20  [human Gate A]
  -> DESIGN-10
  -> DESIGN-20  [human Gate B]
  -> TASK-10
  -> BUILD-10 or BUILD-20
  -> RELEASE-10
  -> AWS-10/20/30 when deployment is in scope
~~~

There are exactly two routine lifecycle gates:

1. **Gate A** accepts a versioned requirements set.
2. **Gate B** accepts the complete PRD and a bounded construction envelope.

AWS mutations, production changes, destructive actions, merges, and other
external side effects may still need action-specific authorization when they
were not explicitly included in the approved construction envelope. Those are
safety authorizations, not extra lifecycle gates.

### Owner quick guide

A Quick MVP is one small, reversible development release. Use `high-risk` when
work involves production, sensitive or regulated data, payments, customer
isolation, shared infrastructure, irreversible data changes, or a potentially
large outage or cost increase. The profile changes scope and review depth; it
never reduces required testing or approval.

An AWS lane describes planned access; it does not authorize a change. AWS
changes require an approved record naming the account, Region, environment,
resources, operations, cost limit, rollback plan, and expiration.

## Start here

For a GitHub-template or extracted-release installation, send `init template`.
BOOT-00 expands that shorthand to **START AWS CODEX FASTLANE**, `Setup:
THIS_REPOSITORY`, and the safely detected local-Git choice. For brownfield
adoption, use
`Setup: ADOPT_EXISTING_REPOSITORY` and an exact absolute target. BOOT-00 safely
initializes or resumes the project, explains the workflow, and immediately
begins the doctor-selected prompt. A new project proceeds directly into its
first guided-intake questions.

For an initialized repository, use the prompt matching the current state. Do
not skip a missing Gate A or Gate B.

## Codex-native skill routing

The implicit `fastlane` skill is the sole application coordinator and writer.
It progressively loads the phase procedure selected by the doctor.
`launch-fastlane`, `plan-fastlane`, and `build-fastlane` are explicit
compatibility aliases that delegate to `fastlane`; they never run separate
lifecycles. `explain-fastlane` and `operate-fastlane-aws` are explicit-only.
`LEARN-10` remains only as a backward-compatible alias for
`explain-fastlane`, never an automatic route. `maintain-fastlane` applies only
to the reusable framework and must not start project intake.

## Agent reference — exact authority and operating model

The repository is authoritative:

| Concern | Authoritative source |
|---|---|
| Scope, engineering rules, and safety | AGENTS.md and applicable nested AGENTS.md files |
| Requirements, analysis, design, gates, and construction envelope | docs/project/PRD.md |
| Active defect contract | docs/project/BUGFIX.md |
| Tasks, dependencies, waves, status, and execution log | docs/project/TASKS.md |
| Evidence actually observed | docs/project/VERIFY.md |
| Deployment, rollback, recovery, operations, and teardown | docs/project/RUNBOOK.md |
| Machine-readable lifecycle and resume mirror | bootstrap.yaml (derived only; never authorization) |
| Durable review and collaboration | GitHub issues and pull requests |
| Runtime behavior | Code, tests, schemas, configuration, and infrastructure |

Notion may launch the prompts and present status, but it is not a second source
of truth. When sources conflict, stop and report the conflict. Do not silently
choose one or create another planning document. A `bootstrap.yaml` mismatch is
a stop condition; never use the mirror to infer approval or widen authority.

Every run declares two independent axes:

- **Project mode:** greenfield or brownfield.
- **Delivery profile:** quick-mvp, standard, or high-risk.

Quick-mvp is the default when the project can be delivered as one small,
reversible development release. Brownfield mode begins with repository
discovery and preserves existing conventions unless an approved requirement
justifies changing them.

Apply the selected delivery profile as an overlay, never as a substitute for
the common safety contract:

| Profile | Planning and construction overlay |
|---|---|
| `quick-mvp` | One thin outcome, one development environment and Region where feasible, the fewest independently verifiable tasks, one coordinator, and release as soon as the approved outcome is safe and observable. |
| `standard` | Complete operational design for the intended environments, explicit integration and migration coverage, and serialized construction by one coordinator. |
| `high-risk` | Deeper review of identity, data access, customer separation, migration, recovery, rollback, shared-resource impact, audit needs, and failure handling; stronger evidence and smaller mutation batches; production or destructive actions remain separately authorized when not already exact. |

Select `high-risk` for production, sensitive or regulated data, payments,
customer isolation, shared infrastructure, irreversible data changes, or a
potentially large outage or cost increase, even if a faster profile was
requested. All profiles still use only Gate A and Gate B as routine lifecycle
gates.

## Common prompt contract

Apply this contract to every prompt below.

### Authorization

- Tool availability, credentials, a task state, a GitHub label, prior access,
  silence, or continued conversation never equals authorization.
- Codex cannot approve its own proposal or fill in an approver identity.
- Reject `Codex`, `agent`, `automation`, `system`, `AI`, and every other model
  or service identity as a gate approver, case-insensitively.
- Local read-only inspection is allowed unless the user restricts it.
- Local writes must be within the prompt's declared write set.
- GitHub reads and writes are separate modes. A write requires the current
  user request or the active construction authorization to name the repository
  and permit that operation.
- AWS documentation lookup, authenticated read-only discovery, and AWS mutation
  are separate modes. Each requires the mode declared by the prompt.
- Never expose credentials or secret values. Never weaken IAM, networking,
  encryption, validation, or logging to make a command pass.
- A material requirements change invalidates Gate A and dependent Gate B.
  A material design or construction-envelope change invalidates Gate B.
  Mark each affected gate `STALE`, increment the affected revision, and return
  to the corresponding gate.

### Exactly accepted gate receipts

Gate A is accepted only when the human sends a receipt equal to this complete
block after trimming surrounding whitespace, with IDs that exactly match the
current proposed requirements card:

~~~text
APPROVE REQUIREMENTS GATE A
Requirements revision: REQ-0001
Cost posture: MINIMIZE_TOTAL_COST; HARD_CAP_NOT_STATED
Accepted assumptions: ASM-... or NONE
Approver: <name/handle>
~~~

Gate B is accepted only when the human sends a receipt equal to this complete
block after trimming surrounding whitespace, with IDs that exactly match the
current proposed design card:

~~~text
APPROVE PRD AND CONSTRUCTION GATE B
Requirements revision: REQ-0001
Design revision: DES-0001
Construction authorization: AUTH-0001
Construction envelope SHA-256: sha256:<64-lowercase-hex>
Use the proposed construction envelope above.
Approver: <name/handle>
~~~

The values shown are examples. The generated card must use the current proposed
IDs, and the human must replace the approver placeholder. Do not accept a
paraphrase, mismatched revision, placeholder approver, partial receipt, silence,
continued conversation, task state, or tool access. Reject extra non-blank
lines, comments, duplicate fields, missing fields, reordered fields, and code
fences around the receipt.

Only the owner can approve either gate. A valid Gate A receipt sets the current
requirements gate to `APPROVED_FOR_DESIGN`. A valid Gate B receipt sets the
current PRD and construction gate to `APPROVED_FOR_CONSTRUCTION`. Codex may
record those receipts but may never create or self-accept them.

When recording a valid receipt, also record its observed ISO 8601 time and the
exact source locator available in the current interaction (for example, a
message, issue, or meeting-record link). Those provenance fields are metadata,
not extra receipt lines. Do not invent a source link or approver identity; if
the source cannot be durably identified, stop and ask the owner how it should
be cited.

For Gate B, compute the digest from the canonical complete construction-envelope
table defined in docs/project/PRD.md: header, separator, and every boundary row in stored
order; trailing whitespace removed per line; LF separators and one final LF;
UTF-8 bytes; SHA-256 lowercase hex. The agent review, owner record, proposed
receipt, and returned receipt must all contain the same digest. Any envelope
change increments AUTH, makes Gate B stale, and requires a new digest and owner
receipt. Before hashing, set the envelope's `Design contract SHA-256` to the
doctor-derived current value. A changed Technology decision, Property
applicability, Property definition, or Property execution table therefore
invalidates that row; correcting it changes the envelope digest and requires
new Gate B approval.

### Exact conditional AWS action receipts

These receipts authorize one bounded external action; they are not additional
routine lifecycle gates. A deployment receipt is required for an
`explicit-gate` mutation. A fast-dev mutation instead must fit the current Gate
B envelope exactly; a mismatch makes Gate B stale and cannot be repaired by an
action receipt. Teardown always requires its own receipt. After trimming
surrounding whitespace, accept only the complete block with actual values,
exact current IDs, no placeholders, and no extra, missing, duplicate,
reordered, commented, or fenced lines.

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

Record a supplied receipt verbatim in the action journal or durable evidence
location named by the active envelope, plus its observed time and source. It
activates only the exact AWS mutation contemplated by the current
`explicit-gate` envelope; it never widens construction scope, local or GitHub
writes, resource boundaries, or platform authority. A deployment receipt never
authorizes teardown. The durable copy is the uniquely marked deployment or
teardown receipt block in docs/project/VERIFY.md. Recompute its SHA-256 from the exact
normalized receipt and require its `Profile or role` and `Approver` to match
the action-authorization row and current approved boundary. A row, digest, or
agent-authored copy cannot substitute for the owner's exact message.

### Construction envelope

Gate B approves only the versioned envelope recorded in docs/project/PRD.md. It must state:

- project mode and delivery profile;
- repository, base branch, branch strategy, and allowed local write boundary;
- task scope, non-goals, and maximum autonomous run boundary;
- allowed GitHub write operations, or NONE;
- AWS mode: NONE, DOCS_ONLY, READ_ONLY, or MUTATION;
- stop conditions, validation commands, and evidence requirements;
- cost, security, data, environment, and destructive-action limits;
- whether merge and branch cleanup are allowed;
- authorization ID and expiry or completion condition.

It also requires a resolvable local Git baseline, explicit protected dirty
paths, exact external-state targets, literal allowed command prefixes, and the
canonical complete-envelope SHA-256. Use docs/project/PRD.md's exact row grammars; do not
replace them with prose or synonyms.

If a fast development deployment is proposed, the envelope must also include
the complete AWS mutation boundary listed below. Otherwise Gate B does not
authorize AWS mutation.

### Canonical AWS mode mapping

The project lane, one prompt's access mode, and Gate B's AWS boundary are
different fields. Use this mapping and no synonyms:

| Project AWS lane | Prompt AWS mode | Gate B AWS boundary |
|---|---|---|
| `documentation-only` | `DOCS_ONLY` | `DOCS_ONLY` |
| `read-only` | `READ_ONLY` | `READ_ONLY` |
| `fast-dev` | `MUTATION` only after AWS-10 preflight | `MUTATE_LISTED_RESOURCES` |
| `explicit-gate` | `DOCS_ONLY` or `READ_ONLY` | `DOCS_ONLY` or `READ_ONLY`; AWS-20 also requires a separate action-specific mutation receipt |

`NONE` means no AWS access in the current prompt. An IaC synth or local plan
does not itself require authenticated AWS mutation.

### AWS grounding and mutation boundary

**Official grounding reviewed July 18, 2026.** Fastlane uses the official
aws-core plugin from Agent Toolkit for AWS:

- [Agent Toolkit for AWS](https://aws.amazon.com/products/developer-tools/agent-toolkit-for-aws/)
- [Agent Toolkit plugins](https://docs.aws.amazon.com/agent-toolkit/latest/userguide/plugins.html)
- [Agent Toolkit AWS CLI setup](https://docs.aws.amazon.com/agent-toolkit/latest/userguide/aws-cli.html)
- [AWS MCP Server tools](https://docs.aws.amazon.com/agent-toolkit/latest/userguide/understanding-mcp-server-tools.html)
- [Multi-profile support](https://docs.aws.amazon.com/agent-toolkit/latest/userguide/multi-account-access.html)

Fastlane uses only the current official plugin identity
`aws-core@agent-toolkit-for-aws` from `aws/agent-toolkit-for-aws`. Do not pin an
AWS Core version or commit. Use AWS Core skills and current primary AWS
documentation before relying on model memory whenever material AWS facts affect
requirements, architecture, Gate B readiness, release planning, deployment,
operations, or teardown. The plugin is a research and tool layer; it does not
replace `docs/project/PRD.md`, the human gates, IAM, or an AWS authorization
record. Its advisory evidence may use the PRD's exact `Design` syntax to bind a
current DES and influenced TECH IDs, but it never selects technology or grants
approval. Its observed version is metadata, not a pin. Fresh templates require
current official `aws-core@agent-toolkit-for-aws` before initialization.
Initialized projects skip the prerequisite gate during normal resume. Missing
or stale AWS Core evidence later pauses only the affected material AWS step and
produces one concise official setup action.
AWS operations remain blocked without the required evidence and authorization.

Before any AWS mutation, the active authorization must state all of:

~~~text
profile or role
account ID or approved alias
Region
environment
stack, application, and resource boundary
approved operation
approved resource summary
artifact authorization and provenance
IaC plan/change-set identifier and digest
billable impact or budget ceiling
prohibited operations
rollback or teardown path
authorization ID, approver, and validity window
~~~

Missing, stale, or conflicting values make the mutation BLOCKED. Read-only
discovery must precede mutation. Prefer a read-only profile by default and the
least-privileged write profile only for an authorized operation.

AWS Core selects a currently supported account-operation tool; never make a
tool name a product dependency or infer a lane from prose. `STRUCTURED_API` is
one attributable operation whose observable service, operation, context,
parameters, and resources fit current doctor-derived authority.
`REVIEWED_SCRIPT` is a legitimate multi-step workflow bound by one current
`AWS-EXEC-*` record in `docs/project/VERIFY.md` to the exact authority and one
script or immutable artifact SHA-256. The record grants nothing. Stale,
duplicate, expired, mismatched, opaque, or unbound scripts remain blocked; a
description never proves script contents. Task polling requires a task ID bound
in derived authority. Presigned URLs require exact resource, direction,
operation, and expiration fit. Exact matches preserve normal owner approval
and IAM. Deployment and teardown remain separate authorities and use their
unchanged exact receipts.

Select IaC checks from the current TECH register: CloudFormation/SAM/CDK synth,
lint, selected Guard/policy validation, and an authorized change set;
Terraform format/validate/selected policy checks and deterministic plan
binding; container dependency, SBOM, and selected image checks; or an exact
approved equivalent. Do not impose universal scanners. IAM Access Analyzer
`ValidatePolicy` is authenticated read-only work at AWS-10 after Gate B.
CloudFormation `CreateChangeSet` creates account-side state and is a mutation;
authorize it separately from `ExecuteChangeSet`. Prefer GitHub OIDC short-lived
role credentials to persistent GitHub AWS secrets. AWS Budgets and billing
alerts are delayed monitoring, not guaranteed spending stops.

Repository trust and managed platform policy still apply. A newly installed or
enabled plugin may require a new Codex session. Reuse an existing official copy
instead of requesting another installation. If setup is needed for AWS design,
use `/plugins`; register a missing marketplace only with the owner-run command
`codex plugin marketplace add aws/agent-toolkit-for-aws`, restart, and resume
with `CONTINUE AWS DESIGN`. Fastlane does not inspect private plugin state,
compare hook hashes, request
screenshots, run synthetic hook probes, or create a hook-trust receipt. For
material decisions, require attributable live AWS Core `retrieve_skill` and
`search_documentation` results rather than generic connectors, cached prose, or
model memory. Installation or explicit `@AWS-Core` selection proves
availability, not use. Only a validated search-then-matching-retrieve chain may
produce concise owner audit attribution; unavailable or unobservable calls
produce no claim. Persist no raw skill content, transcript, credentials,
session identifiers, or machine details.

BOOT-00 does not configure AWS credentials. When an explicitly invoked AWS
operating prompt later needs account access, follow the current Agent Toolkit
flow (`aws configure agent-toolkit`) and allowlist only the intended profiles.
For multiple profiles, the first is the default:

~~~bash
export AWS_MCP_PROXY_PROFILES="mvp-readonly mvp-deploy"
~~~

### Evidence states

Use evidence states that do not overclaim:

~~~text
NOT_STARTED -> IMPLEMENTED -> LOCAL_PASS -> PENDING_AWS -> VERIFIED
                    \-> FAILED | BLOCKED
Any formerly passing state -> STALE when its revision, artifact, environment,
or target identity no longer matches.
~~~

Local tests cannot produce deployed AWS evidence. A task can be DONE when its
approved task-level criteria pass while AWS-only evidence remains PENDING_AWS.
Before any DONE mutation, record each cited local `EV-nnnn` exactly once in
docs/project/VERIFY.md under `Task completion evidence`, with the exact task, observed
command/result, actor, timezone-qualified time, tested commit/worktree/artifact,
durable source, and `LOCAL_PASS` or `VERIFIED`. Placeholder, duplicate,
wrong-task, fenced, URL-only, and non-passing rows grant no completion evidence.

### Human response contracts

Use one response type for the current interaction. Do not combine routine,
gate, and AWS receipts into one wall of metadata.

#### Routine status

Use this for BOOT-00, intake, requirements, design work, tasks, construction,
GitHub synchronization, and release review. Pass the current doctor report as
JSON on stdin to `python scripts/fastlane_presenter.py owner --input-stdin`.
Do not hand-compose lifecycle routing. The presenter uses exactly these owner
fields:

~~~text
FASTLANE · <DEFINE|DESIGN|DELIVER>

Status: <plain-language state>
Updated: <material change or Nothing>
Need from you: <one concrete action or Nothing>
Next: <automatic next work>
Audit: <only consequential evidence; omit otherwise>
~~~

A routine update identifies exactly one next action. `Need from you` names an
owner action only for a genuine decision, setup step, approval, authorization,
protected-boundary decision, or human safety review; otherwise it is `Nothing`.
Include one copyable reply only when owner input is required. Omit `Audit` when
it adds no decision value. Never expose prompt IDs as owner instructions, or
include internal hashes, file counts, repetitive `NONE` values, implementation
narration, or exhaustive AWS authority fields.

The doctor's additive `remediation` object classifies each error with a stable
`DGN-*` ID, responsible party, category, and automatic-correction decision,
then derives one `next_action`. Any `MANUAL_SAFETY_REVIEW` item blocks automatic
correction. Unknown codes fail closed to `HUMAN_REVIEWER`. Safe Codex and owner
items may coexist: correct only independent Codex-owned defects first, preserve
owner-controlled requirements, architecture, technologies, gates, receipts,
and authority, then validate and rerun the doctor. Never infer that manifest
drift followed an authorized maintenance change; only a passing scoped
`maintain-fastlane` preflight permits regeneration.

`Need from you: Nothing` plus `CORRECT_AND_REVALIDATE` means Codex corrects the
reported in-scope defect inside the current write boundary and attempt budget,
reruns validation, and continues. `REVIEW_SAFETY_BLOCKER` is reserved for a
genuine human safety review.

For a side question, answer directly, rerun the doctor, and pass the unchanged
report plus the answer to `python scripts/fastlane_presenter.py side-question
--input-stdin`. State whether project state changed and restore the current next
action. Do not repeat a formal Gate A, Gate B, or AWS receipt merely
because a question was asked. A side question never creates an internal
checkpoint or changes lifecycle state unless the owner separately requested a
project change.

#### Gate receipt

INTAKE-20 and DESIGN-20 return the exact Gate A or Gate B owner receipt defined
above, bound to the current PRD revision. They may precede it with a concise
readiness summary, but must not append a routine status or AWS receipt.

#### AWS authority/evidence receipt

AWS-10, AWS-20, AWS-30, AWS-40, and AWS-50 return this exact field set. Use
actual authorized or observed values; never infer missing authority or evidence:

~~~text
AWS AUTHORITY AND EVIDENCE RECEIPT
Prompt: <AWS-nn>
Construction authorization: <AUTH-nnnn or NONE>
AWS authorization: <AWS-AUTH-nnnn, TEARDOWN-AUTH-nnnn, Gate B fast-dev authority, or READ_ONLY scope>
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

The receipt is revision- and target-bound durable evidence. Do not claim an
action, test, merge, deployment, account observation, or AWS Core result without
direct evidence.

## Prompt index

| ID | Purpose | Normal next |
|---|---|---|
| BOOT-00 | Initialize and explain the fast lane | INTAKE-10 |
| INTAKE-10 | Guided plain-language discovery | REQ-10 or another INTAKE-10 round |
| REQ-10 | Analyze and version requirements | INTAKE-20 |
| INTAKE-20 | Present Gate A | DESIGN-10 |
| DESIGN-10 | Complete the PRD and construction envelope | DESIGN-20 |
| DESIGN-20 | Present Gate B | TASK-10 |
| BUG-10 | Define an evidence-based defect contract | TASK-10 |
| TASK-10 | Produce executable tasks and safe waves | BUILD-10 or BUILD-20 |
| BUILD-10 | Execute one approved task | BUILD-10, RELEASE-10, or STOP |
| BUILD-20 | Run approved tasks autonomously | RELEASE-10 or STOP |
| SYNC-10 | Reconcile authorized GitHub tracking | BUILD-20, RELEASE-10, or STOP |
| RELEASE-10 | Review and, if authorized, finalize the release | AWS-10, AWS-40, or STOP |
| AWS-10 | Read-only deployment preflight | AWS-20 or STOP |
| AWS-20 | Execute an authorized deployment | AWS-30 |
| AWS-30 | Reconcile deployed evidence | RELEASE-10 |
| AWS-40 | Read-only residual and teardown review | AWS-50 or STOP |
| AWS-50 | Execute an authorized teardown | STOP |

---

## BOOT-00 — Bootstrap Launchpad

**Purpose:** Verify prerequisites before a first welcome, safely initialize an
untouched repository, or resume an initialized project at its derived lifecycle
stage. Fresh initialization requires attributable official AWS Core; ordinary
resume does not rerun setup.

**Preconditions:** The owner sent an accepted start or resume command and the
repository or explicit adoption target is locally accessible.

**Accepted commands:** `init template`, `initialize template`, `start
Fastlane`, `continue setup`, and the expanded `START AWS CODEX FASTLANE`
command.

**Authoritative inputs:** Canonical repository and optional adoption-target
paths; manifest and source hashes; bootstrap dry-run; prerequisite,
dependency-check, and doctor JSON; applicable `AGENTS.md` files; Git state;
project source records; and allowlisted, ephemeral capability observations
attributable to official AWS Core in the current Codex session.

**Permitted writes:** For an untouched in-place template, only allowlisted
placeholder rendering after successful source-integrity, path, dirty-file, and
dry-run checks. For a new external target, only manifest-allowlisted files
inside the exact collision-free target. Brownfield collisions require the
existing complete hash-bound adoption record. Never use `--force`, follow a
symlink escape, overwrite an unresolved collision, or regenerate an active
project. BOOT-00 does not write AWS Core evidence.

**GitHub mode:** NONE. Local Git setup is not GitHub authorization.

**AWS mode:** NONE. BOOT-00 does not inspect credentials, access an AWS account,
or invoke AWS account APIs.

**Required authorization:** The start command permits only safe local
initialization or inspection. It does not approve requirements, design,
construction, GitHub activity, plugin changes, hook trust, AWS access, or AWS
mutation.

**Stop conditions:** Fresh prerequisite failure; unsafe or ambiguous roots;
source/target containment; maintainer-source, manifest, hash, symlink,
dirty-template, collision, adoption-record, partial-write, dependency, doctor,
or source-of-truth failure.

**Receipt:** One prerequisite checklist when blocked; otherwise one routine
owner update followed by the questions or work selected by the doctor.

**Next:** Welcome and setup questions after prerequisites, or the exact doctor
route for an initialized project.

~~~text
[BOOT-00]
Process this command:

START AWS CODEX FASTLANE
Setup: <THIS_REPOSITORY|ADOPT_EXISTING_REPOSITORY>
Target path: <required only for ADOPT_EXISTING_REPOSITORY>
Local Git setup: <INIT_AND_BASELINE_COMMIT|USE_EXISTING>

Treat `init template`, `initialize template`, and `start Fastlane` as
`THIS_REPOSITORY`. Treat `continue setup` as an idempotent recheck of one
previous local blocker.

1. Inspect `bootstrap.yaml`, `docs/project/PRD.md`, and repository state
   before owner-facing output.

   If the project is already initialized, do not print the welcome, ask setup
   questions, rerun prerequisites, rerun initialization, or narrate repository
   checks. Run the dependency check and doctor, then resume its `interaction`
   state.

2. Only for an unconfigured template, first run:

   python scripts/setup_assistant.py prerequisites --root <repository root> --json

   Observe current Codex-session capability attribution without reading
   credentials or invoking AWS account APIs. Pass only the setup assistant's
   allowlisted fields through standard input:

   python scripts/setup_assistant.py prerequisites --root <repository root> --evidence-stdin --json

   Search the runtime catalog first with `search_documentation` query `AWS
   skills`, select one canonical identifier from its results, then call
   `retrieve_skill` with that exact identifier. Pass the linked, timestamped
   observations through the nested `aws_core_runtime_discovery` field. Both
   calls must be attributable to `aws-core@agent-toolkit-for-aws` from
   `aws/agent-toolkit-for-aws` and confirm no credential inspection or account
   access. Installation metadata, bundled/local skills, memory, and prose are
   insufficient; a documentation URL is not required merely to prove discovery.
   This exact `AWS skills` search/retrieve chain runs first. Do not run an
   exploratory topic search before it, and do not repeat it after valid setup
   evidence exists. Architecture-specific discovery begins only when a later
   material Define or Design question requires it.

   When blocked, render the returned checklist as one owner action and stop.
   Never execute its installation commands, change plugin state, approve native
   hook trust, inspect private trust storage, or persist its observations.

3. Only after `PREREQUISITES_READY`, run:

   python scripts/setup_assistant.py welcome

   Reproduce stdout exactly once. Collect no more than these three values in
   one reply: project name, preferred AWS Region, and development budget posture.
   Do not paraphrase or repeat those questions. Accept either a finite owner cap
   with ISO currency or "minimize cost; no hard cap." Preserve an owner cap as
   `MINIMIZE_TOTAL_COST; HARD_CAP: <ISO_CURRENCY> <OWNER_AMOUNT>`; otherwise
   use `MINIMIZE_TOTAL_COST; HARD_CAP_NOT_STATED`. Recommend `us-west-2`
   only when the owner is unsure. A budget is a ceiling, not a spending target
   or AWS authorization.

4. Run:

   python scripts/bootstrap_dependencies.py --root <repository root> --json

   This validates repository assets and the official-current AWS Core policy.
   It does not prove plugin installation or grant AWS access. Do not run
   maintainer tests, pytest, installers, or plugin mutations during setup.

5. After all three fresh-template answers arrive, classify the target as
   TEMPLATE_SOURCE, UNCONFIGURED_TEMPLATE, NEW_TARGET, ACTIVE_GREENFIELD,
   ACTIVE_BROWNFIELD, or BLOCKED. For an unconfigured template, dry-run before
   applying:

   python bootstrap.py --target <repository root> --project-name <name> --region <region> --cost-posture "<exact cost posture>" --in-place-template-instance --dry-run
   python bootstrap.py --target <repository root> --project-name <name> --region <region> --cost-posture "<exact cost posture>" --in-place-template-instance

   Preserve Git and user-owned changes. For brownfield adoption, preview every
   collision and require the current complete hash-bound decision map. The
   start command does not authorize `ADOPT_TEMPLATE`. Require:

   CONFIRM BOOTSTRAP ADOPTION PLAN
   schema_version: 1
   source_root: <canonical absolute template source>
   target_root: <canonical absolute target>
   authorized_by: <human owner>
   authorized_at: <RFC 3339 timestamp with timezone>
   authorization_source: OWNER_CONFIRMATION
   plan_sha256: <64 lowercase hex characters>
   Decisions:
   <relative path> | <action> | <expected target SHA-256> | <expected rendered-template SHA-256>

   Compute `plan_sha256` from canonical compact, sorted-key UTF-8 JSON
   containing schema version, both roots, and the complete ordered decision
   map. It never hashes decisions alone or omits that context. Reject missing,
   duplicate, reordered, or drifted paths. Never infer `ADOPT_TEMPLATE`.

6. Run:

   python scripts/bootstrap_doctor.py --root <target> --json

   The doctor is the lifecycle router. Its `interaction` object is the only
   owner stage, response mode, action, continuation, receipt, and AWS Core
   materiality state. Prompt IDs remain internal metadata.

   Route stale state deterministically: Gate A STALE goes to INTAKE-10 when
   owner facts are missing and otherwise REQ-10; a current Gate A receipt
   awaiting approval goes to INTAKE-20; a stale Gate B with current Gate A goes
   to DESIGN-10; approved Gate B with an uninitialized or stale task plan goes
   to TASK-10. Otherwise use the doctor state or stop on conflict. Never restart
   BOOT-00 or prerequisites after initialization.

   Contract migration is Codex-owned generated work, not owner setup. Preserve an unchanged approved schema 1.2 Gate A as the design-only bridge to schema 5, and preserve an unchanged approved schema 4 Gate B for its exact design and envelope.
   Ask the owner only for a missing owner fact, a material requirements decision, or the fresh Gate B required after a design-controlled change.

7. For a routine interaction, render `interaction` through
   `python scripts/fastlane_presenter.py owner --input-stdin`. Return one owner
   action, include a copyable reply when input is required, and omit internal
   prompt IDs, hashes, file counts, command narration, repetitive empty fields,
   and AWS authority data. Use the canonical Gate or AWS receipt instead when
   `formal_receipt_required` is true.

8. Execute the selected action immediately when
   `automatic_continuation_allowed` is true. At first intake, ask one to three
   plain-language questions below the Define update. At later stages, resume
   the selected phase. After each phase checkpoint, rerun the doctor in the
   same turn and repeat this loop until a declared stop condition. A changed
   internal prompt ID is never itself a reason to pause.
   Never ask an initialized project for another `init template` or completed
   setup value.

If current AWS evidence later becomes missing or stale, stop only the affected
material step and give one official AWS Core action. Do not regenerate the
project or rerun the fresh prerequisite gate.

Native hook review is the owner's attestation to the official plugin identity
and hook inventory displayed by Codex. Fastlane never claims to observe a
private trust database; it does not compare hook hashes, request screenshots,
run synthetic probes, or create another product gate.

Do not write requirements, design, tasks, application code, or infrastructure
during BOOT-00. Outside the exact selected local-Git action, do not alter Git.
~~~

## INTAKE-10 — Guided Intake

**Preconditions:** BOOT-00 routed to INTAKE-10 or an existing intake round.

**Authoritative inputs:** Applicable AGENTS.md; existing source-of-truth files; for brownfield,
repository code, tests, IaC, configuration, and recent relevant history.

**Permitted writes:** docs/project/PRD.md Document status mode/profile/risk/lane fields,
workload profile, intake provenance, brownfield contract, and Part I only after
reflecting proposed facts to the user. A material edit to previously approved
requirements must atomically mark both derived gates STALE. No design or task
writes. In the same checkpoint, update the `bootstrap.yaml` mirror and TASKS
Active execution snapshot. Reconcile IN_PROGRESS work before making a plan STALE.

**GitHub mode:** NONE by default; READ_ONLY only when needed to understand an
identified brownfield repository.

**AWS mode:** DOCS_ONLY only when a current AWS fact is needed; no authenticated
AWS access.

**Required authorization:** Intake and its declared local write only.

**Stop conditions:** More than three unanswered questions; secrets appear in
input; repository facts contradict the request; a decision would materially
change scope without human input.

**Receipt:** Routine status.

**Next:** Another INTAKE-10 round or REQ-10.

~~~text
[INTAKE-10]
Guide the user from a rough idea to requirements in short, plain-language
rounds. Read the repository first in brownfield mode and distinguish observed
facts from recommendations.

In each response:
1. summarize the current understanding in at most five bullets;
2. ask at most three questions;
3. ask only questions needed to avoid a material scope, user, outcome, data,
   security, deployment, or success-measure mistake;
4. give two or three understandable choices when helpful;
5. always allow the answer “I'm not sure—recommend one”;
6. recommend a choice only when current evidence justifies it and explain its
   practical effect in one sentence; otherwise state
   `No recommendation—choose the option that matches your situation.`;
7. lead with the real-world consequence and keep unexplained `RTO`, `RPO`,
   `p95`, concurrency, metadata, EARS, QAS, and Harness terminology out of the
   owner response unless the owner used it or asks for technical detail; and
8. include one short copyable reply. Permit the current token-bound
   `R-*; Accept all recommendations.` alternative only when every presented
   default is independently safe and complete.

Before requirements analysis:
- Keep repository mode (`GREENFIELD` or `BROWNFIELD`) separate from owner
  work context (`NEW_APPLICATION`, `EXISTING_APPLICATION_CHANGE`, or
  `REPAIR_OR_MIGRATION`). Empty code never proves a new application.
- Record the seven canonical `INTAKE-*` foundation rows. Only a direct owner
  statement may become a confirmed `OWNER_FACT`; repository observations,
  recommendations, inferred risk, assumptions, and questions remain separate.
- Keep normative requirements provisional while any material foundation field
  or current card question is unresolved.
- Store one current `INTAKE-CARD-*` in PRD intake provenance. Decision rows
  use uppercase A/B/C, one practical effect and tradeoff per option, a
  recommendation only when one is justified, any required supporting detail,
  and an exact reply. When none is justified, show the exact no-recommendation
  sentence above and use `1: <choose A, B, or C>` for that decision in the
  copyable reply. Factual rows use short free text and no invented choices.
- A selection is current only when it is bound to the current card and revision
  with normalized `OWNER_RESPONSE` provenance. A recommendation, assistant
  example, prior owner message, ambiguous shorthand, stale-card reply, or
  absent reply never confirms a choice.
- Before any project write for a possible card answer, run the deterministic
  parser against the exact current card ID, revision, digest, reply token, and a
  new `OWNER-MSG-*` ID. Failure is atomic: make zero writes, preserve the card,
  and return its owner-safe correction without echoing secret-like input.
  Partial success updates only returned reply keys; all others remain pending
  on the same card under their original stable keys.
- Accept bounded ASCII whitespace, lowercase or uppercase A/B/C input normalized
  to uppercase, semicolon or newline separators, factual responses, valid
  partial replies, and the exact safe accept-all phrase. Reject unknown or
  duplicate reply keys, stale card identity or digest, placeholders,
  unresolved sentinel values, secret-like assignments, contradictory choices,
  missing required detail, unsupported whitespace, and unparsed extra content.
- Unapproved legacy intake reopens facts from unconfirmed context, never synthesizes `OWNER-MSG-*` provenance, and grandfathers only unchanged approved Gate A.
- An unchanged approved schema 1.2 Gate A may remain the exact requirements basis for a design-only schema 5 migration. Do not reopen intake or ask the owner to repeat confirmed facts unless a current required owner fact is absent.
- The `Accept all recommendations.` payload selects only complete
  recommendations when preceded by the exact current reply token, every
  question is a decision, and no selected option needs detail. Do not offer or
  accept it for factual questions, missing recommendations, required detail,
  partial eligibility, an altered phrase, or a stale token/card.
- Project each successful parsed answer into the normalized owner-response
  register, the matching card row, and every foundation row named by that
  question's basis IDs. All foundation facts derived from one question cite the
  same parsed owner-response record. For the initial work-context question, map
  `A` to `NEW_APPLICATION`, `B` to `EXISTING_APPLICATION_CHANGE`, and `C` to
  `REPAIR_OR_MIGRATION`. This provenance proves deterministic interpretation
  and current-card binding; it does not authenticate the owner's identity.
- If the owner asks for advice or says `recommend one`, explain the options
  and practical tradeoff, state that project state did not change, and restore
  the unchanged card.
- When `interaction.turn_boundary_required` is true, the rendered card is the
  final action of the assistant turn. Do not call another tool, edit the PRD,
  rerun the Engine, interpret the copyable example, or continue until a new
  inbound owner message arrives.

Capture:
- owner work context: new application, existing application change, or
  repair/migration, independent of repository mode;
- project mode: greenfield or brownfield;
- delivery profile: quick-mvp, standard, or high-risk;
- users, problem, observable outcome, and success measures;
- in-scope behavior and explicit non-goals;
- data sensitivity, identity boundary, integrations, and failure impact;
- environment, Region constraints, cost sensitivity or a real hard cap, and release expectation;
- brownfield compatibility, migration, and operational constraints.

For quick-mvp, propose a thin first release: one primary actor, one observable
outcome, one core entity or state transition, one entry point, one Region, one
development environment, measurable requirements, explicit non-goals, and one
rollback/teardown path.

Default cost posture to `MINIMIZE_TOTAL_COST; HARD_CAP_NOT_STATED`. Ask about a
hard cap only when the owner says one exists or a material choice cannot be
made without it. Preserve a supplied cap's exact ISO currency and amount as
`MINIMIZE_TOTAL_COST; HARD_CAP: <ISO_CURRENCY> <OWNER_AMOUNT>`; for example,
an owner-provided USD 20.00 cap becomes
`MINIMIZE_TOTAL_COST; HARD_CAP: USD 20.00`. A missing amount alone never blocks intake.
Security, recovery, and evidence requirements are not
negotiable cost tradeoffs.

Do not ask the user to choose an AWS service unless that choice is itself a
business constraint. Do not design, generate tasks, or seek approval yet.
When the material intake gaps are closed, state that intake is ready for REQ-10.
Return the routine status.
~~~

## REQ-10 — Requirements Analysis

**Preconditions:** Intake has enough information to define a bounded outcome.

**Authoritative inputs:** AGENTS.md; docs/project/PRD.md; intake facts; brownfield code/tests/IaC/config;
current AWS Core capability and primary documentation needed to validate
external constraints; read-only requirements-review findings.

**Permitted writes:** docs/project/PRD.md requirements-revision-controlled content plus the
Document status requirements revision and derived Gate A/Gate B states;
docs/project/TASKS.md's Active execution snapshot identity, Gate B, run-stop, and next-action
fields only. Update the summary, detailed analysis, task snapshot, and matching
`bootstrap.yaml` lifecycle mirror as one coordinator checkpoint. Do not
generate a replacement graph. When invalidating an existing plan, reconcile
IN_PROGRESS tasks to DONE with evidence or BLOCKED with the revision reason,
commit/archive the stopped ledger, then mark its Task-plan state STALE.

**GitHub mode:** READ_ONLY only if authorized and needed for brownfield facts.

**AWS mode:** DOCS_ONLY; authenticated AWS access is not required.

**Required authorization:** Requirements analysis and declared docs/project/PRD.md writes only.

**Stop conditions:** Unresolved contradiction; missing critical security/data
boundary; unverifiable outcome; requested requirement is infeasible or unsafe;
or a material AWS feasibility fact needed for Gate A remains unverified.

**Receipt:** Routine status with proposed REQ revision.

**Next:** INTAKE-10 when blocked; otherwise INTAKE-20.

~~~text
[REQ-10]
Analyze the entire intake as one requirement set before technical design.

First run `python scripts/bootstrap_dependencies.py --root . --json`. The
coordinator challenges the complete requirement set. Quick MVP uses no
subagent by default. Invoke the read-only
`fastlane-requirements-challenger` only for ambiguity, contradictions,
sensitive data, identity, payments, migrations, shared interfaces, high risk,
or an explicit owner request, and only after the complete draft exists with no
open owner decision. Make one attempt per requirements revision and wait no
more than 60 seconds. If it fails, stalls, or is unavailable, stop it, record
`Independent requirements challenge: UNAVAILABLE — coordinator checklist completed`
in the current Gate A Recommendation rationale, perform the checklist as the
coordinator, rerun the doctor and deterministic presenter, and continue. Never
expose reviewer timing or orchestration or turn its availability into an owner
action. When AWS feasibility, Region, identity, data
protection, recovery, or cost materially affects readiness, the coordinator
uses official AWS Core directly with current primary AWS documentation. If AWS
Core is unavailable, continue ordinary
requirements work and mark only the unresolved material AWS fact as open. The coordinator evaluates any challenger
findings and remains the only writer. A challenger cannot approve Gate A.

Translate only normative requirement rows into the Fastlane EARS Contract in
the current PRD table and select exactly one `GHERKIN` or `MEASURABLE`
acceptance form. Keep product statements, stories, goals, non-goals, facts,
findings, assumptions, open decisions, architecture, tasks, tests, receipts,
evidence, and authorization metadata outside that contract. For material performance,
availability, reliability, recovery, scalability, security-response, or
operational-response concerns, complete a `QAS-*` row; otherwise record
`NOT_APPLICABLE — <concrete reason>`. Apply STRIDE, LINDDUN, ATAM, or ADR only
when the phase reference's material trigger is met. Record results in existing
authorities and add no methodology-specific stage, gate, or document. Keep all
methodology names out of routine owner responses unless the owner explicitly
asks for an explanation.

Complete the PRD schema 1.3 actor, journey, conditional rich-use-case, business-rule, acceptance-ID, and requirement-coverage records. Ask only for missing product facts; never expose the internal method profile or invent them.

Create or increment a requirements revision such as REQ-0001. Give every
requirement, non-goal, assumption, and material open question a stable ID.
Derive the internal Adaptive Coverage Plan from the work kind, delivery profile,
risk, requirements, and repository facts. Do not ask a new routine question.
Every omission needs a current basis; uncertain impact uses full coverage.
Record in docs/project/PRD.md:
- problem, actors, outcome, scope, and non-goals;
- measurable functional and non-functional requirements;
- security, privacy, data, failure, concurrency, recovery, observability,
  performance, cost posture and any real hard cap, accessibility, and regional
  constraints where applicable;
- brownfield compatibility and migration constraints;
- acceptance criteria and objective verification method for each requirement;
- assumptions explicitly proposed for acceptance;
- contradictions, ambiguities, undefined terms, missing cases, and feasibility;
- relevant AWS Well-Architected impacts.

Fill the Gate A readiness card with these exact fields: Outcome; Owner and
users; Scope and non-goals; Measurable requirement/acceptance IDs; Data
boundary; Identity/security boundary; Environment/Region; Failure/recovery;
Cost posture; Intake provenance. Every value must be explicit and trace to the
current revision. Use `NOT_APPLICABLE — <reason>` only when genuinely
inapplicable; a blank, TODO, TBD, UNKNOWN, or bare NONE keeps readiness BLOCKED.
`MINIMIZE_TOTAL_COST; HARD_CAP_NOT_STATED` is explicit and ready when no hard
cap is an owner requirement. When one exists, preserve the owner's exact
currency and amount as
`MINIMIZE_TOTAL_COST; HARD_CAP: <ISO_CURRENCY> <OWNER_AMOUNT>`; `USD 20.00` is
only an example. Do not manufacture a numeric ceiling for Gate A.

For brownfield mode, do not mark ready until repository/baseline,
deployments, architecture/ownership, interfaces/consumers, data/migration,
security controls, baseline commands/evidence, and protected components are
observed and explicit. Only drift, dirty changes, known debt/defects, and
overlay collisions may use the exact nullable forms defined in docs/project/PRD.md.

Set readiness to exactly one:
- BLOCKED;
- READY_WITH_PROPOSED_ASSUMPTIONS;
- READY_FOR_OWNER_APPROVAL.

Do not silently resolve contradictions, choose architecture, approve
assumptions, or mark Gate A accepted. If blocked, set Gate A to `BLOCKED` and
ask at most three plain questions using the INTAKE-10 style. When either ready
recommendation is recorded, atomically set both the Document status and detailed
Gate A owner state to `PENDING_OWNER_APPROVAL`, keep Gate B `BLOCKED` for a new
project or `STALE` after invalidating an earlier design. Mirror both gate states
in bootstrap.yaml and copy the current REQ plus non-runnable Gate B state into
docs/project/TASKS.md's Active execution snapshot. Reset the Gate A owner decision to
`PENDING`, clear any prior approver/provenance/authorization fields, and render
the current proposed receipt with an approver placeholder; never carry an old
receipt into a new revision. Existing tasks become non-runnable and an active
run becomes `BLOCKED`; never silently retarget them to the new revision. Set the
reconciled plan STALE, then prepare a concise Gate A decision brief for
INTAKE-20. Return the routine status.
~~~

## INTAKE-20 — Requirements Gate A

**Preconditions:** REQ-10 produced a current requirements revision that is not
BLOCKED.

**Authoritative inputs:** Current docs/project/PRD.md requirements, analysis, assumptions, and revision.

**Permitted writes:** docs/project/PRD.md Gate A owner record and the matching Document
status Gate A state only after receiving an exact valid receipt. Update both
and the matching `bootstrap.yaml` lifecycle mirror as one coordinator
checkpoint. docs/project/TASKS.md remains non-runnable; update only its identity/state
snapshot if needed to repair a mirror mismatch, never task blocks.

**GitHub mode:** NONE.

**AWS mode:** DOCS_ONLY when current AWS evidence is needed; no AWS account
access.

**Required authorization:** Presentation only until the human sends the exact receipt.

**Stop conditions:** BLOCKED readiness; stale or mismatched ID; placeholder
approver; altered or partial receipt; requirements change during review; or a
material AWS feasibility fact required by the readiness card is stale or
unverified.

**Receipt:** Exact Gate A receipt after a concise readiness summary. Do not append a routine status or AWS receipt.

**Next:** DESIGN-10 only after exact acceptance; otherwise REQ-10 or INTAKE-10.

~~~text
[INTAKE-20]
Present the current requirements for human Gate A.

Show a concise decision brief:
- requirements revision and delivery profile;
- all ten fields from the current Gate A readiness card;
- user outcome and measurable success;
- in scope and non-goals;
- accepted-fact candidates versus proposed assumptions;
- security, data, cost, deployment, and brownfield constraints;
- unresolved risks that do not block the gate;
- material AWS feasibility facts verified through AWS Core, their sources, and
  any advisor finding the coordinator rejected with its reason;
- what Gate A does and does not approve.

Do not approve the gate yourself. Render a copyable receipt using the exact
field names below and the actual current IDs. List every assumption ID or NONE.
The human must replace the approver placeholder.

Accept Gate A only if the human response equals the complete block below after
trimming surrounding whitespace:

APPROVE REQUIREMENTS GATE A
Requirements revision: REQ-0001
Cost posture: <exact current Gate A cost posture>
Accepted assumptions: ASM-... or NONE
Approver: <name/handle>

The revision, cost posture, and assumptions must exactly match the proposed
card. Reject extra or duplicate fields, comments, reordered lines, partial
blocks, and code fences.
Silence, continued conversation, task state, or tool access never counts. After
a valid receipt, preserve the complete normalized receipt inside the uniquely
marked Gate A receipt block, copy its exact cost posture into the detailed
owner record, then atomically update that record, Document status, and lifecycle
mirror to APPROVED_FOR_DESIGN. Record the
observed ISO 8601 authorization time and exact message/issue/meeting-record
source as structured provenance without adding either value to the receipt.
Do not invent a source. After acceptance, return the exact recorded Gate A
receipt and do not combine it with a routine response. Then rerun the doctor in
the same turn and begin Design without requesting another owner message merely
to cross the internal route. Before acceptance, put the exact proposed Gate A
receipt last after a concise readiness summary.
~~~

## DESIGN-10 — Technical PRD and Construction Envelope

**Preconditions:** Current Gate A receipt.

**Authoritative inputs:** Applicable AGENTS.md, PRD, VERIFY, relevant brownfield
artifacts/history, current official AWS Core/docs, and read-only findings.

**Permitted writes:** PRD Parts III/IV, envelope, and DES/AUTH/Gate B status;
one ADR if needed; VERIFY evidence; TASKS snapshot; and bootstrap.yaml mirror,
as one coordinator checkpoint. Do not generate tasks; reconcile active work.

**GitHub mode:** READ_ONLY only when authorized for design facts.

**AWS mode:** DOCS_ONLY by default; authenticated READ_ONLY only when explicitly
authorized for a brownfield environment.

**Required authorization:** Design writes only; no implementation, GitHub
writes, or AWS mutation.

**Stop conditions:** Missing/invalid Gate A; requirements/design conflict;
incomplete/stale architecture, traceability, TECH, or property contract;
wrong/unavailable AWS Core; missing/failed/stale DESIGN-10
`search_documentation`/`retrieve_skill` evidence; or unverified AWS claim.

**Receipt:** Routine status with REQ, DES, and proposed AUTH IDs.

**Next:** REQ-10 for material scope changes; otherwise DESIGN-20.

~~~text
[DESIGN-10]
Complete a build-ready technical PRD for the accepted requirements.

Create/increment DES and proposed AUTH IDs. Confirm
`aws-core@agent-toolkit-for-aws`. For each material AWS question, identify
basis IDs, call `search_documentation`, review returned descriptions, select
the smallest relevant set, and call `retrieve_skill` with exact returned
identifiers. Follow the retrieved procedure and current official references.

Record linked `AWS-DISC-*` chains in docs/project/VERIFY.md. Search precedes
retrieve; basis, identity, actor, results, privacy, time, binding, and exact
returned/selected IDs match. Bind every `AWS-EV-*` to its chain and use
`DES-0001; TECH: TECH-0001, TECH-0002` or
`DES-0001; TECH: NONE — no technology/toolchain impact`; observed AWS Core version is metadata, never a pin.
Persist no raw skill content or transcripts;
installation, BOOT metadata, cache, connectors, and memory are insufficient.
Codex is the only writer and selects the design.

After completing the proposed design, use `fastlane-architecture-challenger`
only when conditionally triggered; it cannot select, write, approve,
authorize, or replace evidence.

Load the Design reference, follow the Adaptive Coverage Plan, and complete
required PRD records. `SELECT` compares complete candidates; `AMEND` revalidates
affected drivers/alternatives; `PRESERVE` proves architecture, technology,
trust, data, recovery, Region, and Harness boundaries unchanged.

Apply the compatibility boundary first. An unchanged approved schema 4 Gate B
remains current for its exact design/envelope. New, unapproved, or
design-controlled work requires schema 5, new digests, and fresh Gate B.
With a current approved legacy schema 1.2 Gate A, Codex may migrate schema 5
without changing Part I. Generated migration is Codex-owned: report
`Need from you: Nothing` unless an owner fact is missing; never invent it,
change requirements, expand authority, or bypass task/Harness/evidence checks.

- For SELECT, evaluate a secure managed-serverless baseline. Complete `DRV-*`,
  `CAND-*`, selected `ARCH-*`, traceability, and `AWS-EV-*`; apply
  hard constraints before preferences and select only an eligible candidate.
- Record rejected alternatives, risks/mitigations, Security impact,
  Reliability impact, Operational burden, cost/breakpoints, Migration path,
  revisit triggers, and validation across required whole-system domains.
- Complete in-scope `TECH-*`. Only `EXACT` accepts opaque versions; Active `PROPERTY_TESTING` uses
  `EXACT`, `COMPATIBLE_MAJOR`, or numeric `MINIMUM`.
- classify every measurable Gate A requirement exactly once. Each applicable
  `PROP-*` has one bounded local command without shell-control
  chaining; its replay format must explicitly declare a seed or deterministic reproduction and VERIFY target.
- Complete the Gate B Harness Profile and Change impact record. Uncertain
  impact uses `FULL_REVALIDATION`; resolve brownfield compatibility,
  migration, and protected behavior.

- Complete material interface and layer-boundary contracts, every applicable state model, and the NEW_BUILD first-wave/spike record. Bind them into the current design digest before Gate B.

Update existing PRD Mermaid blocks in place, name the selected `ARCH-*` as the
shared basis, and not append by default. Route material Part I flow changes through REQ-10. Preserve least-privilege IAM, encryption, secrets, validation,
safe failures, telemetry, low-usage cost, billing dimensions, scaling
breakpoints, and measurable expansion or migration
triggers. Never weaken one of those required controls to lower cost.

Fill the Gate B readiness card with these exact fields: Design basis IDs;
Architecture/components; Technology/toolchains/version policy; Interfaces/data
flow; Identity/secrets; Failure/retry/concurrency; Deployment/operations;
Validation/evidence; Rollback/recovery/teardown; Brownfield
compatibility/migration; Outstanding gaps. Use explicit stable IDs.
`NOT_APPLICABLE — <reason>` is allowed only when genuine. Outstanding gaps is
`NONE` or stable gap IDs; any gap keeps Gate B `BLOCKED`.

Propose every construction-envelope row with the PRD's exact grammar. GitHub
merge/branch deletion remain unauthorized unless listed; AWS defaults
DOCS_ONLY. Fast-dev mutation requires non-production, exact
resources/operations, a finite positive ceiling within the owner's cap and
currency, feasible rollback/teardown, authorized SHA-256 provenance, future
expiry, and the exact
`ENVIRONMENT: <exact>; CLASS: NON_PRODUCTION`,
`EXACT_DIGEST: sha256:<64 lowercase hex>` or
`DERIVED_FROM_AUTHORIZED_SOURCE: SHA-256 from baseline <full authorized commit>; <deterministic rule>`,
and `Expires at <ISO 8601 with timezone>; earlier completion: <exact condition>` grammars.

Require local Git and a baseline. Hash Architecture driver, Candidate,
Selection, Traceability, Material AWS evidence, Harness, Change impact,
Technology, Property applicability, definition, and execution tables into the
Design contract SHA-256. Copy it to the envelope; include the selected `ARCH-*`,
current `TECH-*`, and applicable `PROP-*` in `SCOPE_IDS`. Hash the complete
envelope and copy it to the Gate B review and proposed receipt.

Incomplete design/envelope keeps Gate B `BLOCKED`. Only after the recommendation
is `READY_FOR_CONSTRUCTION_APPROVAL`, atomically set the
Document status DES/AUTH/design/Gate B fields and owner Gate B state to
`PENDING_OWNER_APPROVAL`; copy current REQ/DES/AUTH, Gate B state, and authorized maximum
workers, baseline, and protected dirty paths into docs/project/TASKS.md's Active
execution snapshot and bootstrap.yaml. Keep old tasks stale until approved and TASK-10
replaces them. Reset the owner decision to `PENDING`, clear old approval
provenance/receipts, never carry an old receipt into a new design or AUTH, and
render the current proposed receipt. Do not implement,
generate tasks, approve, or perform GitHub/AWS writes. Return routine status.
~~~
## DESIGN-20 — PRD and Construction Gate B

**Preconditions:** Complete, internally consistent PRD; current Gate A;
proposed DES revision and AUTH envelope.

**Authoritative inputs:** docs/project/PRD.md in full, including traceability and proposed
envelope; current AWS Core capability; recorded primary AWS sources and
read-only advisor findings.

**Permitted writes:** docs/project/PRD.md Gate B owner record and the matching Document
status Gate B state only after an exact valid human receipt. Update both
plus docs/project/TASKS.md's Active execution snapshot and the matching `bootstrap.yaml`
lifecycle mirror as one coordinator checkpoint. Do not generate or rewrite
task blocks.

**GitHub mode:** NONE.

**AWS mode:** DOCS_ONLY through the current AWS Core session; no AWS account
access.

**Required authorization:** Presentation only until the exact receipt is received.

**Stop conditions:** Stale Gate A; incomplete design/envelope; mismatch between
requirements, design, or IDs; placeholder approver; altered/partial receipt;
diagram-to-design conflict; unexplained generic roles or unused optional
diagram paths;
or material AWS design evidence is stale or unverified.

**Receipt:** Exact Gate B receipt after a concise readiness summary. Do not append a routine status or AWS receipt.

**Next:** TASK-10 only after exact acceptance; otherwise DESIGN-10 or REQ-10.

~~~text
[DESIGN-20]
Review the complete PRD and proposed construction envelope for human Gate B.

Show a concise decision brief:
- REQ, DES, and AUTH IDs;
- canonical complete construction-envelope SHA-256;
- all current readiness-card fields;
- architecture and key tradeoffs;
- confirmation that the existing diagram slots were specialized in place and
  agree with the component, interface, data, and failure design;
- material AWS facts verified through AWS Core, primary sources, and any AWS
  advisor finding the coordinator rejected with its reason;
- requirement-to-design/test traceability;
- security, data, availability, cost, migration, rollback, and teardown risks;
- project mode and delivery profile;
- exact local, GitHub, AWS, merge, branch-cleanup, and autonomous-run boundaries;
- explicit exclusions and stop conditions.

Set the Gate B agent recommendation to exactly `BLOCKED` or
`READY_FOR_CONSTRUCTION_APPROVAL`. The recommendation is advisory and does not
approve the gate.

Do not approve the gate yourself. Render a copyable receipt with the exact
field names below and actual current IDs. The human must replace the approver
placeholder.

Accept Gate B only if the human response equals the complete block below after
trimming surrounding whitespace:

APPROVE PRD AND CONSTRUCTION GATE B
Requirements revision: REQ-0001
Design revision: DES-0001
Construction authorization: AUTH-0001
Construction envelope SHA-256: sha256:<64-lowercase-hex>
Use the proposed construction envelope above.
Approver: <name/handle>

All IDs and the canonical complete-envelope SHA-256 must exactly match the
proposed card and structured owner record. Reject extra or duplicate fields,
comments, reordered lines, partial blocks, and code fences. Silence, continued
conversation, task state, or tool access never counts. After a valid receipt,
preserve the complete normalized receipt inside the uniquely marked Gate B
receipt block, then atomically update the detailed owner record, Document
status, docs/project/TASKS.md Active execution snapshot, and lifecycle mirror to
APPROVED_FOR_CONSTRUCTION. Record the observed ISO 8601 authorization time and
exact message/issue/meeting-record source as structured provenance without
adding either value to the receipt. Do not invent a source. Activate only that
envelope, and ensure the task snapshot contains the exact REQ/DES/AUTH IDs,
approved Gate B state, authorized maximum workers, baseline, protected dirty
paths, and `TASK-10` as the next safe action while the plan state is
UNINITIALIZED or STALE.
After acceptance, return the exact recorded Gate B receipt. Before acceptance,
put the exact proposed Gate B receipt last after a concise readiness summary.
After recording an accepted receipt, rerun the doctor in the same turn and
continue through task generation and permitted local construction without
requesting another owner message merely to cross the internal route.
~~~

## BUG-10 — Active Defect Contract

**Preconditions:** Reproducible symptom or bounded investigation request; an
active construction authorization is required before implementation.

**Authoritative inputs:** AGENTS.md; docs/project/BUGFIX.md; relevant docs/project/PRD.md requirements; code, tests,
logs supplied by the user, configuration, IaC, and relevant history.

**Permitted writes:** docs/project/BUGFIX.md defect analysis and regression contract only.

**GitHub mode:** READ_ONLY only when authorized and necessary for evidence.

**AWS mode:** NONE by default; READ_ONLY only with explicit environment scope.

**Required authorization:** Analysis only. This prompt never authorizes a fix or external
write.

**Stop conditions:** Evidence requires secrets; production mutation would be
needed to reproduce; symptom suggests active incident/data loss; scope becomes
a feature or material requirements change.

**Receipt:** Routine status.

**Next:** TASK-10 if covered by active Gate B; otherwise REQ-10.

~~~text
[BUG-10]
Define an evidence-based defect contract without implementing the fix.

Record in docs/project/BUGFIX.md:
- stable bug ID, observed behavior, expected behavior, and business impact;
- reproducible evidence and confidence;
- affected versions/environments and smallest known boundary;
- root-cause hypotheses clearly separated from facts;
- security, privacy, data-loss, concurrency, migration, and rollback risk;
- regression acceptance criteria and validation commands;
- relationship to accepted PRD requirements and current AUTH envelope.

Inspect before hypothesizing. Do not manufacture logs or claim reproduction you
did not observe. If the correction changes accepted behavior or exceeds the
active envelope, return to REQ-10. Otherwise state readiness for TASK-10 and
return the routine status.
~~~

## TASK-10 — Executable Task Plan

**Preconditions:** Valid current Gate B receipt and active construction
authorization; or a defect fully covered by that authorization.

**Authoritative inputs:** AGENTS.md; docs/project/PRD.md; docs/project/BUGFIX.md when applicable; current code/tests/IaC;
docs/project/TASKS.md; docs/project/VERIFY.md; docs/project/RUNBOOK.md; bootstrap.yaml; passing bootstrap doctor output.

**Permitted writes:** docs/project/TASKS.md and its matching `bootstrap.yaml` task-plan mirror
as one checkpoint; no implementation.

**GitHub mode:** NONE. Planning GitHub objects is allowed, creating them is not.

**AWS mode:** NONE, except DOCS_ONLY for validation-command accuracy.

**Required authorization:** Task planning within active AUTH scope.

**Stop conditions:** Gate/revision mismatch; task would exceed envelope; unsafe
dependency; validation cannot objectively prove acceptance; or planning would
select or substitute a technology, version policy, or property execution value.

**Receipt:** Routine status.

**Next:** BUILD-10 for one task or BUILD-20 for an autonomous run.

~~~text
[TASK-10]
Translate the accepted PRD or BUGFIX contract into executable docs/project/TASKS.md entries.

Tasks trace to approved EARS requirement IDs, but task cards are not EARS and
must not add an `EARS form`, `INVEST`, `THIN_SLICE`, or `DEFINITION_OF_DONE`
metadata field. Apply the Fastlane INVEST profile from the Deliver reference.
Prefer a Thin Vertical Slice when the selected architecture permits it; do not
force one onto a legitimate migration-only, security-only,
infrastructure-only, or evidence-only task. Every exception still has one
coherent outcome and independent evidence.

For `NEW_BUILD`, wave 1 implements the approved first end-to-end journey. One bounded disposable spike may precede it only when the Gate B record says it blocks that path; it cannot replace or satisfy the product outcome.
Include the approved `WAVE-*` ID in that walking-skeleton task's `Requirements` metadata.

Plan each task so the unchanged Fastlane Definition of Done can be satisfied:
all acceptance criteria, exact validation, applicable property tests, observed
evidence, approved boundaries, current execution log and checkpoint, no
unresolved blocker or placeholder, and complete required documentation and
runbook changes. Do not repeat these method labels as new task metadata.

Run the read-only bootstrap doctor first. Task-plan state is exactly
UNINITIALIZED, CURRENT, or STALE. Set the next monotonic Task-plan revision such
as PLAN-0001 and change state to CURRENT only after the complete replacement
graph validates. If the old state is STALE, first reconcile every IN_PROGRESS
task, checkpoint and commit the non-runnable graph, add its plan/REQ/DES/AUTH and
archive commit to the registry, then replace the current graph without reusing
task IDs.

For every task include:
- stable ID and outcome;
- status: BACKLOG, READY, IN_PROGRESS, BLOCKED, DONE, or SKIPPED;
- requirement/bug, applicable acceptance/journey/PROP and wave/spike traceability, plus the existing `Design`
  value as `DES-0001; TECH: TECH-0001, TECH-0002` or
  `DES-0001; TECH: NONE — no technology/toolchain impact`;
- current AUTH ID, dependencies, and explicit skipped-dependency waivers or NONE;
- exact write set and external-state set;
- acceptance criteria;
- validation commands and required evidence;
- risk class, AWS mode, attempt budget/used count, owner, run ID, blocker,
  skip record, and checkpoint fields;
- GitHub link or PENDING_SYNC;
- concise execution log.

TASK-10 is copy-only for design decisions. Copy relevant TECH IDs and every
applicable property execution value exactly from the approved PRD. Never choose
or substitute a technology, framework, version policy, command, run target,
seed/reproduction format, or evidence destination. Missing or incompatible
values route to DESIGN-10.
Copy every required or triggered conditional `HARNESS-*` row into the
applicable task's existing `#### Validation` section: Harness ID, basis IDs,
exact command or API, trigger, and VERIFY destination. Do not add Harness
metadata fields or a separate task merely to repeat the profile. A missing,
changed, or incompatible harness value routes to DESIGN-10.


For every applicable `PROP-*`, include its ID in `Requirements`, keep it in the
same implementation task when practical, and copy its exact command, run
target/time bound, seed or reproduction format, framework TECH ID, and VERIFY
destination into an exact Property execution projection table under
`#### Validation`; also put the exact command once in that section's fenced
command list. The table uses the PRD Property execution headers and one copied
row per referenced property:
`Property ID | Framework TECH ID | Exact command | Run target/time bound | Seed or reproduction format | Evidence destination`.
A
property may be omitted only when DESIGN-10 records `NOT_APPLICABLE` with a
concrete reason. Do not add a separate property-test task merely to inflate the
graph.

Emit each record in the validator's exact human-first shape: one
`### <TASK-ID> — <title>` heading; visible Status, Owner, Blocker, and GitHub
issue fields; `#### Outcome`, `#### Acceptance criteria`, `#### Validation`, and
`#### Execution log`; then a collapsed `#### Agent execution details` section
containing every remaining singleton metadata line from docs/project/TASKS.md's Required
task record schema, spelled exactly once. A READY task cannot contain TODO in its outcome,
acceptance criteria, validation, boundary, or traceability. Acceptance criteria
must be checkboxes, and a DONE task must have every acceptance checkbox checked,
non-NONE Evidence, and an observed execution-log entry.

In a CURRENT plan, fully resolve the outcome, acceptance criteria, validation,
boundaries, REQ/DES/AUTH trace, applicable TECH decisions, and property
projection for every BACKLOG task as well. BACKLOG means dependency-gated, not
undefined: it contributes to approved plan coverage, never appears in
`--ready`, and cannot be claimed until it explicitly becomes READY. The stock
UNINITIALIZED placeholder is exempt, and SKIPPED tasks do not satisfy property
coverage.

Keep tasks thin enough to validate independently. Mark READY only when all
dependencies, inputs, and authorization are satisfied. A SKIPPED dependency is
not satisfied without a current waiver naming the dependency, downstream task,
authority, rationale, and replacement evidence. Compute structural waves, then
preserve their dependency order, and execute them serially through one
coordinator. Set `Maximum workers` to `1`. The coordinator is the only writer
for implementation files, docs/project/TASKS.md, docs/project/VERIFY.md,
docs/project/RUNBOOK.md, bootstrap.yaml, and shared controls. Do not create
GitHub objects, implement code, or access AWS. Validate task graph consistency
with `python scripts/task_waves.py docs/project/TASKS.md`, inspect candidates with
`python scripts/task_waves.py docs/project/TASKS.md --ready --json`, commit the validated
current plan locally within the Gate B command/write boundary, update Last
known-green and the checkpoint registry, and rerun the doctor. Never push or
touch a remote unless separately authorized. Return the routine status.

`Maximum workers: 1` limits task claims and mutable execution. A conditional
challenger may run synchronously at its defined checkpoint as a read-only
critic; it is not a worker, claims no task, changes no state, and cannot select
architecture, approve or authorize, or satisfy AWS evidence.
~~~

## BUILD-10 — Execute One Task

**Preconditions:** Named READY task on a CURRENT plan; valid current AUTH;
dependencies complete; write and external-state sets are available; local Git
baseline resolves.

**Authoritative inputs:** Applicable AGENTS.md; task-linked PRD/BUGFIX sections; task entry;
relevant code, tests, IaC, docs/project/VERIFY.md, docs/project/RUNBOOK.md, bootstrap.yaml, and doctor output.

**Permitted writes:** Named task write set; coordinator-serialized updates to
docs/project/TASKS.md, docs/project/VERIFY.md, and bootstrap.yaml; docs/project/RUNBOOK.md only when repeatable
operations change.

**GitHub mode:** Only operations explicitly allowed by current AUTH or current
user instruction.

**AWS mode:** As stated by current AUTH. AWS mutation still requires a complete
active mutation boundary.

**Required authorization:** One named task inside AUTH scope.

**Stop conditions:** Scope drift; unexpected shared writer; failed safety check;
new requirement/design decision; technology, toolchain, framework, version
policy, or property-execution substitution; missing authorization;
destructive/billable impact outside boundary; repeated failure without a new
hypothesis.

**Receipt:** Routine status with validation evidence.

**Next:** BUILD-10, RELEASE-10, or STOP.

~~~text
[BUILD-10]
Execute task <TASK-ID> and no unrelated task.

Before editing, run doctor and verify its READY state, dependencies (DONE or an
explicitly waived SKIPPED prerequisite), exact write set, active REQ/DES/AUTH
IDs, and external authorization. Use the coordinator tool rather than hand
editing run or claim fields. Allocate the next unused monotonic IDs and replace
the illustrative IDs below, then run this exact start-and-claim sequence:

```bash
python scripts/task_waves.py docs/project/TASKS.md --start-run RUN-0001 --coordinator codex-coordinator --run-mode SINGLE_TASK
python scripts/task_waves.py docs/project/TASKS.md --claim TASK-0001 --owner codex-coordinator --run-id RUN-0001 --coordinator codex-coordinator --checkpoint CP-0000
```

If the same run is safely checkpointed instead of new, reconcile the checkpoint
and use this exact resume-and-claim sequence:

```bash
python scripts/task_waves.py docs/project/TASKS.md --resume-run RUN-0001 --coordinator codex-coordinator
python scripts/task_waves.py docs/project/TASKS.md --claim TASK-0001 --owner codex-coordinator --run-id RUN-0001 --coordinator codex-coordinator --checkpoint CP-0002
```

A persisted `RUNNING` run is interrupted/recovery-required and must not be
started over or automatically resumed. Claiming atomically records owner, run
ID, base checkpoint, and the incremented persistent attempt before editing.
Inspect before changing code and make the smallest coherent implementation.
Confirm the task's `Design` value and copied property execution values exactly
match the approved PRD. Resolve an exact installed version only within its
selected version policy. If a selected technology, framework, toolchain,
version, command, run target, or replay method is unavailable or incompatible,
mark the task BLOCKED and route to DESIGN-10; never substitute it during BUILD.

Run the task's validation plus relevant regression, security, IaC, and failure
checks. For every task-linked `PROP-*`, run the approved property suite with the
exact PRD command and run target/time bound. Record one `EV-nnnn` property row
using the exact VERIFY schema: same task and REQ/DES/AUTH trace, property,
framework TECH ID and selection, observed exact version, command, `CASES: <n>;
ELAPSED_SECONDS: <seconds>`, replay data, minimized counterexample, failure resolution,
result, observed ISO time, commit/worktree/artifact, and durable source. The
observed version must satisfy the approved version policy. A PASS must meet the
planned threshold and use `NONE` for counterexample and failure. On failure,
preserve and classify the counterexample as
`IMPLEMENTATION_DEFECT`,
`SPECIFICATION_AMBIGUITY_OR_DEFECT`, `GENERATOR_OR_ORACLE_DEFECT`, or
`ENVIRONMENT_DEFECT`. Fix implementation or test machinery and rerun when the
approved semantics and boundary remain unchanged; never delete the failure.
The latest uniquely timed row for the task/property pair must PASS before DONE.
Give every property row a matching Task completion evidence row: `FAILED` for a
failed observation, and `LOCAL_PASS` or `VERIFIED` for a passing observation.
Only the passing status may be cited to complete the task.
Run every task-linked required or triggered conditional `HARNESS-*` check by
its exact approved command or API and record a Harness execution evidence row
with its current basis, artifact/environment, result, time, and durable source.
Preserve failures and append passing reruns; never replace a failed observation
or weaken the selected check. A requirement or design change routes to REQ-10
or DESIGN-10.
If the requirement,
invariant, or design must change, stop and route to REQ-10 or DESIGN-10; never
weaken the property or generator simply to pass.

Record observed evidence in the exact docs/project/VERIFY.md `Task completion
evidence` table before citing its EV ID. Update docs/project/RUNBOOK.md only if a
repeatable procedure changed. Mark DONE only when every acceptance criterion
and required local check passes; otherwise mark BLOCKED with the next useful
action. Reconcile the task first, then checkpoint the run; never pause with an
IN_PROGRESS task:

```bash
python scripts/task_waves.py docs/project/TASKS.md --set-status TASK-0001 DONE --evidence EV-0001 --run-id RUN-0001 --coordinator codex-coordinator --checkpoint CP-0001
python scripts/task_waves.py docs/project/TASKS.md --pause-run RUN-0001 --coordinator codex-coordinator --checkpoint CP-0002
```

Use `--complete-run RUN-0001 --coordinator codex-coordinator --checkpoint
CP-0002` instead of `--pause-run`
only when every task is terminal. For a blocked attempt, use `--set-status
TASK-0001 BLOCKED --blocker "<observed blocker and next action>" --run-id
RUN-0001 --coordinator codex-coordinator --checkpoint CP-0001`, then pause.
Leave AWS-only evidence PENDING_AWS until observed.

Each claim cites the current base checkpoint. Each `IN_PROGRESS` reconciliation
consumes the next unique checkpoint. Pause or completion consumes a later
unique checkpoint and requires the newest checkpoint row plus VERIFY reference.
Run start and issue synchronization do not invent checkpoints; never reuse one.

Before pausing, inspect the final diff, record `EV-0001`-style evidence, commit
only the authorized validated task changes, and update Last known-green commit
and the checkpoint row to that commit. Run doctor after those updates. Do not
commit a protected dirty path or use a remote Git operation unless separately
authorized.

Perform only GitHub actions listed in the active authorization. BUILD-10 never
executes an AWS mutation directly: if the task reaches a mutation boundary,
record and checkpoint the local state, route through AWS-10 and AWS-20, and use
AWS-30 to reconcile evidence. A connected tool does not grant permission. Stop
on any common-contract condition. Return the routine status.
~~~

## BUILD-20 — Autonomous Construction Run

**Preconditions:** Valid Gate B; active AUTH explicitly permits autonomous
execution; docs/project/TASKS.md plan is CURRENT and its graph is valid; at least one READY
task; local Git baseline resolves.

**Authoritative inputs:** All sources required by eligible tasks; bootstrap.yaml;
passing doctor output; last clean coordinator checkpoint.

**Permitted writes:** Eligible task write sets; coordinator-only serialized writes to
docs/project/TASKS.md, docs/project/VERIFY.md, docs/project/RUNBOOK.md, bootstrap.yaml, shared manifests, lockfiles, schemas,
generated output, and other shared paths.

**GitHub mode:** Only operations explicitly listed in AUTH; no merge or branch
deletion unless named.

**AWS mode:** AUTH boundary only. AWS mutations are always serialized.

**Required authorization:** Autonomous work only until the envelope completion/expiry,
task boundary, or stop condition.

**Stop conditions:** No READY task; envelope exhausted/expired; revision drift;
shared-write collision; failing mainline; new material decision; any technology,
version-policy, or property-execution substitution; unexpected cost/security/data
impact; AWS identity mismatch; destructive step not explicit; approved attempt
budget exhausted without a materially new hypothesis.

**Receipt:** One routine status per completed wave and a final receipt.

**Next:** Continue BUILD-20, SYNC-10, RELEASE-10, or STOP.

~~~text
[BUILD-20]
Run the approved task graph autonomously inside the active construction
authorization until completion or a stop condition.

Allocate the next unused monotonic run ID and acquire it with this exact command
shape before selecting work:

```bash
python scripts/task_waves.py docs/project/TASKS.md --start-run RUN-0001 --coordinator codex-coordinator --run-mode AUTONOMOUS
python scripts/task_waves.py docs/project/TASKS.md --safe-ready --json
```

On a safely PAUSED or BLOCKED run, reconcile state and resume only the same run
and coordinator:

```bash
python scripts/task_waves.py docs/project/TASKS.md --resume-run RUN-0001 --coordinator codex-coordinator
```

Before each claim, require the task's `Design` value and copied property
execution values plus required or triggered conditional Harness Profile values
to match the approved PRD. BUILD-20 may resolve an installed
version only within the selected policy; it cannot substitute a technology,
framework, toolchain, command, run target, or replay method. Block the task and
route to DESIGN-10 on any mismatch or unavailable selection.

Use this loop:
1. run doctor and reconcile PRD, docs/project/TASKS.md, bootstrap.yaml,
   REQ/DES/AUTH, baseline, protected dirty paths, task states, and the external
   operation journal;
2. atomically acquire one durable coordinator run ID; a pre-existing RUNNING
   state is recovery-required and is never auto-cleared;
3. select exactly one READY task whose dependencies are DONE or explicitly
   waived SKIPPED prerequisites, then claim it as the coordinator:

   ```bash
   python scripts/task_waves.py docs/project/TASKS.md --claim TASK-0001 --owner codex-coordinator --run-id RUN-0001 --coordinator codex-coordinator --checkpoint CP-0000
   ```

4. implement only that task's approved write boundary, run its validations, and
   run every copied required or triggered conditional `HARNESS-*` command or
   API, then record observed completion and Harness execution evidence;
5. mark the task DONE only when acceptance evidence passes; otherwise checkpoint
   the blocker and remaining attempt budget;
6. after every task is reconciled out of IN_PROGRESS, inspect the integrated
   diff, record EV evidence, and update the last known-green checkpoint;
7. when all tasks are terminal, run
   `--complete-run RUN-0001 --coordinator codex-coordinator --checkpoint CP-0002`.
   Otherwise run `--pause-run RUN-0001 --coordinator codex-coordinator
   --checkpoint CP-0002`, run doctor and aggregate tests, then resume the
   same run and coordinator. Never run doctor against a persisted RUNNING
   snapshot or commit protected dirty paths.

No subagent may edit implementation files, shared controls, protected or dirty
paths, manifests, lockfiles, schemas, generated output, or GitHub state.
Deterministic task and evidence checks—not reviewer prose—decide readiness and
completion. Journal every external operation before execution. Reconcile
UNKNOWN or partial results read-only before retrying. Keep GitHub operations
within AUTH. Route AWS mutation through AWS-10/AWS-20.

After every reconciled task or wave, rerun the doctor, derive progress only
from its task totals and task-ID fields through `fastlane_presenter.py`, and
continue the next READY task in the same turn when the owner action is
`NONE_CONTINUE_AUTOMATICALLY`. Continue through safe waves without asking
routine questions. Pause only for a declared stop condition or authority that
Gate B did not grant. Return concise routine progress at wave boundaries and a
final routine status.
~~~

## SYNC-10 — GitHub Reconciliation

**Preconditions:** Repository identity is verified; task IDs are stable; current
user instruction or AUTH explicitly permits named GitHub writes.

**Authoritative inputs:** docs/project/TASKS.md; docs/project/VERIFY.md; existing GitHub issues, project items, branches,
checks, and pull requests in the named repository.

**Permitted writes:** Authorized GitHub objects; docs/project/TASKS.md link/status reconciliation.

**GitHub mode:** READ_ONLY when no write authorization; otherwise only listed
WRITE operations.

**AWS mode:** NONE.

**Required authorization:** Repository plus allowed operations must be explicit.

**Stop conditions:** Repository mismatch; issue/task conflict; protected branch
or required check failure; requested merge/close/delete not authorized.

**Receipt:** Routine status listing exact observed GitHub actions.

**Next:** BUILD-20, RELEASE-10, or STOP.

~~~text
[SYNC-10]
Reconcile local task truth with GitHub using stable task IDs.

Read first. For each non-trivial task, update or create only the GitHub objects
allowed by the active authorization. Preserve dependencies, wave, status,
blockers, PR links, and concise validation evidence. Do not copy full logs.
When local and GitHub state conflict, report and reconcile from observed facts;
do not silently overwrite.

Creating branches, issues, project items, commits, pushes, PRs, labels,
comments, merges, releases, or deletions are distinct write operations. Perform
only those explicitly named. Tool availability is never authorization. Return
the routine status.
~~~

## RELEASE-10 — Release Readiness and Finalization

**Preconditions:** Intended release tasks are DONE or explicitly excluded;
aggregate local validation is available; release target is identified.

**Authoritative inputs:** docs/project/PRD.md; docs/project/BUGFIX.md; docs/project/TASKS.md; docs/project/VERIFY.md; docs/project/RUNBOOK.md; diff; tests; IaC;
dependency/security results; authorized GitHub checks.

**Permitted writes:** docs/project/VERIFY.md release assessment; docs/project/RUNBOOK.md only for corrected
procedures; authorized GitHub PR/release actions.

**GitHub mode:** READ_ONLY by default; WRITE only for operations named by AUTH
or the current user. Merge and branch cleanup require explicit inclusion.

**AWS mode:** NONE or DOCS_ONLY. Deployment belongs to AWS-20.

**Required authorization:** Assessment is local; external finalization follows the active
GitHub scope.

**Stop conditions:** Failed required check; unmitigated critical risk; missing
rollback; evidence gap; scope/revision drift; unauthorized merge/release.

**Receipt:** Routine status with READY or BLOCKED and the exact release
state `NOT_READY`, `READY_TO_DEPLOY`, or `RELEASE_VERIFIED` in Validation.

**Next:** AWS-10 only from READY_TO_DEPLOY; AWS-40 after verified deployment
when residual review is in scope; otherwise STOP.

~~~text
[RELEASE-10]
Assess the release against the accepted REQ/DES/AUTH revisions.

Verify:
- requirement and defect acceptance traceability;
- example tests, required PROP evidence, failure paths, security, IaC, and packaging;
- current observed evidence for every required or triggered conditional
  `HARNESS-*` row, using the exact approved command or API;
- each applicable IaC/delivery check selected by current TECH decisions, with
  exact artifact/plan evidence and no substituted universal scanner;
- migration, rollback, recovery, observability, and cost readiness;
- documentation and version consistency;
- GitHub review and required checks when accessible;
- which evidence is LOCAL_PASS versus PENDING_AWS.

Each applicable `PROP-*` requires an observed passing result, framework or
suite, case or run count, and reproducible seed or command. A prior failure also
retains its minimized counterexample and classified resolution. Missing or
unresolved property evidence keeps the release NOT_READY.

Set exactly one release state in docs/project/VERIFY.md: NOT_READY when any required evidence
is incomplete/failed/stale; READY_TO_DEPLOY when all pre-deployment evidence is
current for the immutable artifact and AWS deployment is the only remaining
required step; RELEASE_VERIFIED only when every required local and deployed
acceptance item is VERIFIED or explicitly not applicable. Record observed
evidence and return READY or BLOCKED with specific reasons.
If authorization explicitly permits finalization, perform only the named
GitHub operations after required checks pass. Never infer permission to merge,
publish a release, delete a branch, or deploy. Return the routine status.
~~~

## AWS-10 — Read-Only Deployment Preflight

**Preconditions:** RELEASE-10 recorded `READY_TO_DEPLOY` for the intended immutable artifact; target account,
Region, environment, and stack are named; authenticated read access is
explicitly authorized.

**Authoritative inputs:** docs/project/PRD.md; docs/project/VERIFY.md;
docs/project/RUNBOOK.md; IaC; deployment artifact; official
`aws-core@agent-toolkit-for-aws` skills/docs; read-only AWS identity,
configuration, quotas, target state, and the current DES/TECH validation contract.

**Permitted writes:** docs/project/VERIFY.md preflight evidence only.

**GitHub mode:** NONE or authorized READ_ONLY for artifact/check identity.

**AWS mode:** READ_ONLY. Documentation grounding may accompany it; no mutation.

**Required authorization:** Exact read-only account/profile/Region/environment scope.

**Stop conditions:** Identity mismatch; missing or wrong-source plugin/tool;
missing, failed, cached, generic, or stale AWS-10 `retrieve_skill` or
`search_documentation` evidence; unavailable Region or quota; drift; unreviewed
change set; cost/rollback uncertainty; or any mutation.

**Receipt:** AWS authority/evidence receipt with READY or BLOCKED and observed identity.

**Next:** AWS-20 only with valid mutation authorization; otherwise STOP.

~~~text
[AWS-10]
Perform a read-only AWS deployment preflight. Confirm current official AWS
Core, then create fresh artifact-bound `AWS-DISC-*` chains for the material
operational, deployment, IAM, service, Region, quota, security, reliability,
rollback, teardown, and cost questions. Search first, select the smallest
relevant returned skill set, retrieve those exact identifiers, and follow the
procedures and current official references. BOOT-00 or DESIGN-10 evidence,
installed-skill metadata, cache, connectors, and memory are insufficient.

Record linked rows under `## AWS Core evidence` with one shared Discovery ID,
basis IDs, official source and identity, observed semantic version, actor
`CODEX_LIVE_TOOL_CALL`, discovered identifiers, privacy declarations, Design
trace, ISO 8601 times, PASS/FAIL, and current immutable-artifact binding.
Search must precede retrieval; selected and returned identifiers must match and
appear in search results. Bind each chain to `ARTIFACT: sha256:<64 lowercase
hex>; DES: DES-nnnn; TECH: TECH-nnnn, TECH-nnnn` or the defined no-impact
form. Missing, stale, mismatched, unattributed, or wrong-binding evidence
blocks AWS execution planning. Do not persist raw skill content, transcripts,
credentials, local paths, usernames, trust data, or machine information.

Confirm without exposing secrets:
- caller identity, allowlisted profile/role, account, Region, and environment;
- artifact digest and IaC validation;
- TECH-selected IaC evidence: CloudFormation/SAM/CDK checks, Terraform
  format/validate/policy and deterministic plan boundary, container
  dependency/SBOM/image checks, or the approved equivalent;
- an existing authorized change set or equivalent immutable read-only plan;
- authenticated IAM Access Analyzer `ValidatePolicy` results for generated IAM
  policies when applicable, recorded as `API: accessanalyzer.ValidatePolicy`;
- service availability, quotas, naming, IAM boundary, encryption, networking,
  logging, alarms, backups, and data-retention implications;
- estimated low-usage cost, billing dimensions, scaling breakpoints, and the
  exact authorization ceiling for any proposed mutation;
- rollback and teardown commands and retained-resource behavior;
- absence of unexpected drift or shared-resource impact.

Do not create a CloudFormation change set here; `CreateChangeSet` creates
account-side state and belongs to AWS-20 under exact mutation authority. Do not
create, update, delete, deploy, rotate, migrate, or mutate data. Record
only observed facts in docs/project/VERIFY.md. Return READY only when the complete mutation
boundary can be authorized; otherwise BLOCKED. Return the AWS authority/evidence receipt.
~~~

## AWS-20 — Authorized Deployment

**Preconditions:** AWS-10 READY; active fast-dev envelope or action-specific
authorization contains every AWS mutation-boundary field and matches preflight.

**Authoritative inputs:** Current REQ/DES/AUTH; docs/project/VERIFY.md; docs/project/RUNBOOK.md; artifact; preflight;
aws-core docs/tools; live read-only target state.

**Permitted writes:** Authorized AWS target; docs/project/VERIFY.md IaC/action evidence; docs/project/TASKS.md status;
docs/project/RUNBOOK.md only for observed procedural correction.

**GitHub mode:** Only separately authorized deployment-status/check operations.

**AWS mode:** MUTATION, limited to exact authorization.

**Required authorization:** A valid Gate B fast-dev envelope or a current human
action receipt equal to the complete `AUTHORIZE AWS DEPLOYMENT` block in the
common contract and naming all mutation-boundary fields, including the exact
artifact and IaC plan/change-set binding. Tool access is
insufficient.

**Stop conditions:** Any field mismatch; authorization expired; unexpected
change set/cost/resource; alarm or smoke-test failure; rollback condition;
operation expands scope; destructive replacement not explicitly allowed.

**Receipt:** AWS authority/evidence receipt listing exact mutations and identifiers,
without secrets.

**Next:** AWS-30, including after rollback or partial failure.

~~~text
[AWS-20]
Execute only the AWS deployment authorized by <AWS-AUTH-ID or active fast-dev
AUTH-ID>.

For `explicit-gate`, first compare the supplied owner message to the exact
`AUTHORIZE AWS DEPLOYMENT` block in this pack. Reject placeholders, extra or
missing lines, field-order changes, a stale AUTH, or any value that differs from
AWS-10. Record the valid receipt verbatim with its observed time and exact
source in docs/project/VERIFY.md's marked deployment block, recompute its digest, and
match its role/profile and approver before mutation. Under `fast-dev`, prove
instead that the final action is
fully and exactly contained in the current Gate B mutation envelope; otherwise
mark Gate B stale and route to DESIGN-10. An action-specific receipt cannot
repair a fast-dev envelope mismatch.

Reconfirm caller identity, account, Region, environment, artifact digest, exact
plan/change-set binding, finite positive cost ceiling, owner-cap compatibility, and rollback
path immediately before mutation. The ceiling covers the authorization-validity
period; delayed AWS Budgets/billing alerts are monitoring, not guaranteed
provider stops. Use
the least-privileged approved write profile. Execute the documented deployment
method; do not improvise broader permissions or resources.

Prefer an approved GitHub OIDC role with short-lived credentials over persistent
GitHub AWS secrets. For CloudFormation, treat `CreateChangeSet` and
`ExecuteChangeSet` as separate allowed operations. Creation requires mutation
authority; execute only the reviewed identifier whose canonical plan digest
matches the receipt. Bind Terraform saved plans to reviewed inputs/state mode,
and container deployments to the immutable image digest and selected SBOM/image
checks. Record the observed row in `IaC validation evidence` using
`API: cloudformation.CreateChangeSet` when that API is called.

Stream concise milestones. Stop on every declared threshold. If a rollback
condition occurs, perform rollback only when the authorization includes it;
otherwise stop and report the safest state. Capture command/result identifiers,
resource identifiers, timestamps, alarms, and smoke-test outcomes without
secrets. Do not mark deployed verification complete in this prompt. Return the
AWS authority/evidence receipt and proceed to AWS-30.
~~~

## AWS-30 — Deployed Evidence Reconciliation

**Preconditions:** AWS-20 attempted a deployment or rollback; read-only target
access remains authorized.

**Authoritative inputs:** Deployment receipt; docs/project/PRD.md acceptance criteria; docs/project/VERIFY.md; docs/project/RUNBOOK.md;
live read-only AWS state, telemetry, logs, and smoke-test endpoints.

**Permitted writes:** docs/project/VERIFY.md; docs/project/TASKS.md evidence/status; docs/project/RUNBOOK.md only for repeatable
procedural correction.

**GitHub mode:** Only authorized status/check/comment updates.

**AWS mode:** READ_ONLY. Any corrective mutation requires a new or still-valid
explicit mutation authorization.

**Required authorization:** Exact read-only target scope.

**Stop conditions:** Identity mismatch; telemetry unavailable; security/data
anomaly; failed acceptance test; correction would mutate AWS.

**Receipt:** AWS authority/evidence receipt with `COMPLETE` or `BLOCKED`; put
`VERIFIED`, `PENDING_AWS`, or failed evidence states in Validation and Open
risks, not in the receipt's Observed results field.

**Next:** RELEASE-10 after recording evidence. RELEASE-10 decides whether the
release is RELEASE_VERIFIED, still NOT_READY, or needs an authorized correction.

~~~text
[AWS-30]
Reconcile deployed AWS evidence against the accepted requirements.

Observe:
- deployed artifact/version, exact plan/change-set binding, and resource state;
- CloudFormation stack events or equivalent operation history and terminal status;
- smoke tests and user-visible outcome;
- IAM, encryption, network exposure, logging, alarms, and error signals;
- data integrity, migration, retry/idempotency, and recovery signals as relevant;
- performance and cost indicators available in the observation window, noting
  billing and AWS Budgets delay rather than treating an alert as a hard stop;
- rollback status after a failed deployment.

Record what was actually observed, when, where, and by which read-only identity.
Mark VERIFIED only with objective evidence. Keep unavailable or time-dependent
checks PENDING_AWS. Do not mutate to repair a failed check. Do not set the
release state here. Return the AWS authority/evidence receipt whose Next is RELEASE-10.
~~~

## AWS-40 — Residual Resource and Teardown Review

**Preconditions:** Deployment, test, rollback, or environment lifecycle creates
a need to assess residual resources; read-only target access is authorized.

**Authoritative inputs:** docs/project/PRD.md retention requirements; docs/project/VERIFY.md; docs/project/RUNBOOK.md; IaC state;
live read-only inventory, dependencies, backups, retention, and billing signals.

**Permitted writes:** docs/project/VERIFY.md teardown assessment; docs/project/RUNBOOK.md only for a corrected
repeatable plan.

**GitHub mode:** NONE or authorized status-only writes.

**AWS mode:** READ_ONLY. No deletion or mutation.

**Required authorization:** Exact read-only account/Region/environment/resource boundary.

**Stop conditions:** Shared ownership unclear; retained/regulated data; unknown
dependency; identity mismatch; teardown would cross the named boundary.

**Receipt:** AWS authority/evidence receipt with residual inventory and authorization
requirements.

**Next:** AWS-50 only with explicit teardown authorization; otherwise STOP.

~~~text
[AWS-40]
Perform a read-only residual-resource and teardown review.

Identify:
- the IaC/stack-derived expected removal and retention manifest;
- resources created, changed, retained, shared, or drifted;
- stack events or equivalent operation history and terminal status;
- dependencies and deletion order;
- data, backups, snapshots, domains, certificates, logs, and secrets affected;
- deletion protection and retention requirements;
- continuing billing dimensions;
- exact resources that should be retained versus removed;
- reversible checkpoints and post-teardown verification.

Record inventory/discovery scope and blind spots, including unsupported resource
types, permission limits, account/Region boundaries, and eventual consistency.
An empty query does not prove absence outside that observed boundary.

Compare live inventory to IaC and docs/project/RUNBOOK.md. Do not delete, disable, detach,
empty, rotate, or mutate anything. Produce the exact proposed teardown boundary
and required authorization fields. Return the AWS authority/evidence receipt.
~~~

## AWS-50 — Authorized Teardown

**Preconditions:** AWS-40 complete; current human authorization explicitly names
the resources/stack, retained data, destructive operations, account, Region,
profile/role, cost effect, and validity window.

**Authoritative inputs:** AWS-40 inventory; docs/project/PRD.md retention rules; docs/project/VERIFY.md; docs/project/RUNBOOK.md; live
read-only identity and target state.

**Permitted writes:** Authorized AWS deletions/mutations; docs/project/VERIFY.md; docs/project/TASKS.md; docs/project/RUNBOOK.md
only for observed procedural correction.

**GitHub mode:** Only separately authorized status updates.

**AWS mode:** MUTATION limited to exact teardown authorization.

**Required authorization:** Current action-specific teardown authorization. A deployment
authorization does not imply teardown permission. The human message must equal
the complete `AUTHORIZE AWS TEARDOWN` block in the common contract.

**Stop conditions:** Resource/identity mismatch; shared or retained dependency;
unexpected data; scope expansion; protection requiring an unauthorized change;
partial failure that changes the safe order.

**Receipt:** AWS authority/evidence receipt with removed, retained, failed, and
post-teardown observed resources.

**Next:** STOP, or AWS-40 for residual read-only review.

~~~text
[AWS-50]
Execute only teardown operation <TEARDOWN-AUTH-ID>.

Before mutation, compare the supplied owner message to the exact `AUTHORIZE AWS
TEARDOWN` block in this pack. Reject placeholders, extra or missing lines,
field-order changes, stale IDs, or a value that differs from AWS-40's observed
inventory. Record the valid receipt verbatim with its observed time and exact
source in docs/project/VERIFY.md's marked teardown block, recompute its digest, and
match its role/profile and approver. Gate B fast-dev, a deployment receipt,
credentials, and prior cleanup
discussion never substitute for this receipt.

Reconfirm identity and exact resource inventory immediately before mutation.
Preserve every resource/data class marked retained. Use the documented order
and least-privileged approved profile. Do not disable safeguards or force
deletion unless that exact action is authorized.

After each bounded step, inspect results and stop on mismatch. Perform
post-teardown read-only verification. Reconcile the expected manifest, stack
events/terminal status, removed and retained resources, snapshots/backups,
residuals, and inventory/discovery limits in `Teardown reconciliation evidence`.
Never claim deletion from a submitted request
alone. Return the AWS authority/evidence receipt.
~~~

## Suggested model selection

Model availability changes; verify current options with /model and the official
[Codex model guide](https://developers.openai.com/codex/models). The operating
rule reviewed July 14, 2026 is:

~~~text
Think and review with Sol.
Build with Terra.
Synchronize and maintain with Luna.
~~~

Use the lowest reasoning level that reliably handles the risk. Prefer Sol with
high or extra-high reasoning for requirements, architecture, release review,
security, IAM, migrations, concurrency, destructive work, and difficult
failures. Prefer Terra medium/high for normal implementation and read-only AWS
preflight. Use Luna for bounded mechanical synchronization. Use optional read-only challengers only at their defined planning checkpoints;
the coordinator remains the sole repository writer.
