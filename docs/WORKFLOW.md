# AWS Codex Fastlane Workflow

Fastlane turns an idea into owner-approved requirements, an AWS-informed
technical design, and a build constrained by an explicit construction boundary.

## Start

Send:

```text
init template
```

For a fresh template, Codex first verifies the CLI login, Git, Python,
platform sandbox tools, `uvx`, and official AWS Core. Missing dependencies are
returned together as one owner-run checklist. After they pass, Codex welcomes
the owner and asks once for:

1. one-line project name (ordinary punctuation and international text are supported);
2. canonical AWS Region ID (for example, `us-west-2`); and
3. development budget posture.

Use a finite cap with currency when one exists, or answer
`minimize cost; no hard cap`. Codex initializes the project, runs the Fastlane Engine,
and immediately begins the next lifecycle prompt. A configured project skips
fresh prerequisites and resumes its derived stage.

The repository state and the owner's work are separate facts. After setup,
Fastlane asks whether the owner is starting a new application, changing an
existing one, or repairing/migrating a system; an empty repository does not
answer that question. It then grounds intake in the users, problem, observable
outcome, first-release boundary, success measure, and material data/operating
boundaries. Decisions use no more than three plain-language A/B/C choices with
one exact reply; factual questions remain short free text.

The Engine projects one current card from PRD intake provenance. Rendering it
ends that assistant turn. Only a new owner message can resolve the card, and a
choice that requires a name, service area, fallback, or other supporting detail
remains open until the detail is supplied. Recommendations and examples never
become owner confirmation. Requirements stay provisional until the foundation
and current card are complete.

Fastlane does not assume that option A is a default. When evidence supports a
recommendation, the card marks it and explains its main tradeoff. Otherwise it
says `No recommendation—choose the option that matches your situation.` and
shows a neutral reply such as `1: <choose A, B, or C>`.

When the owner replies to a pending card, the Engine parses that message against
the exact current card before writing project state. It accepts bounded
whitespace, lowercase or uppercase A/B/C choices, semicolon or newline-separated
answers, factual answers, and valid partial replies. It rejects unknown or
duplicate keys, stale-card replies, placeholders, contradictory choices,
missing required detail, unresolved sentinel values, secret-like assignments,
and extra unparsed text. A rejected reply changes no project file and returns
one owner-safe correction without echoing the input. A valid partial reply
records only the supplied answers and leaves the other questions pending under
their original stable reply keys.

The `Accept all recommendations.` payload is safe only after the current reply
token and when every question is a decision with a complete recommendation
that needs no supporting detail. It is unavailable for factual questions or a
partially recommended card. For the initial work-context question, normalized A/B/C choices map to
`NEW_APPLICATION`, `EXISTING_APPLICATION_CHANGE`, and `REPAIR_OR_MIGRATION`.
The normalized response register, card row, and all foundation facts derived
from that question share one current-card provenance record. That record proves
how Fastlane interpreted the message; it does not authenticate the owner's
identity.

For unapproved legacy intake, prior values remain unconfirmed context: Codex
reopens the affected facts and asks the smallest current card rather than
inventing historical owner-response provenance. An unchanged approved Gate A
remains grandfathered until a requirements-controlled change and may bridge
directly into current design work without asking the owner to repeat confirmed
facts.

## Lifecycle

| Phase | Outcome | Owner decision |
|---|---|---|
| BOOT-00 | Repository initialized or safely resumed | Fresh setup answers; none on resume |
| INTAKE-10 / REQ-10 | Requirements, assumptions, cost posture, safeguards, and success criteria | Answer questions |
| Gate A / INTAKE-20 | Exact requirements revision reviewed | Approve requirements for design |
| DESIGN-10 | Technical PRD, current AWS evidence, and construction envelope | None until ready |
| Gate B / DESIGN-20 | Exact design and construction boundary reviewed | Approve construction |
| TASK-10 / BUILD | Dependency-aware tasks run inside the approved boundary | No task-by-task approval |
| RELEASE-10 | Release evidence evaluated | Only when the release contract requires it |
| AWS-10 | Read-only deployment preflight | Authorize the exact read-only account, role or profile, Region, resources, operations, and expiry; no mutation |
| AWS-20 | Exact authorized deployment mutation | Current fast-dev Gate B envelope or separate exact explicit-gate action receipt, after observed preflight |
| AWS-30 | Read-only deployment evidence reconciliation | Authorize the exact read scope only when no current reusable read receipt covers it |
| AWS-40 | Residual-state review, teardown readiness, and terminal reconciliation | Choose a residual disposition when required; authorize the exact read scope when needed |
| AWS-50 | Exact authorized teardown mutation | Separate exact expiring teardown authorization |

Before a modern task plan becomes `CURRENT`, Fastlane accounts for every
approved first-release requirement. The Engine derives one disposition per
requirement from exact task traceability or current no-task evidence. Missing
or mismatched coverage sends Codex back through task replanning; it does not
create another owner gate.

Gate A — approve requirements → Gate B — approve the PRD and construction boundary → Codex builds autonomously inside that boundary.

BUG-10 and SYNC-10 are current-request-scoped adjunct prompts, not Engine
routes or extra lifecycle gates. Codex may use BUG-10 only for an explicitly
requested bounded defect contract and SYNC-10 only for explicitly requested,
authorized named GitHub reconciliation. It preserves the current Engine route
and pending owner action, performs only the adjunct's bounded work, reruns the
Engine, and resumes the derived route. BUILD-10 may advance to BUILD-20 when
the Engine permits autonomous continuation; BUILD-20 may continue itself until
RELEASE-10 or a declared stop condition.

## Internal precision and delivery methods

Owners continue answering short, plain-language questions. Internally, Codex
translates normative requirements through the Fastlane EARS Contract with Gherkin or
measurable acceptance and adds quality-attribute scenarios only when material.
TASK-10 applies Fastlane's INVEST profile, prefers thin vertical slices when
appropriate, and uses the existing DONE transition as the Definition of Done.
TDD, Mikado, STRIDE, LINDDUN, ATAM, and ADR are conditional techniques, not
lifecycle stages or approval gates. Their outputs stay in the existing PRD,
task, decision, test, and evidence authorities.

At Gate A, Fastlane derives one internal coverage record from the work kind,
approved requirements, risk, and repository facts. New builds receive a full
architecture comparison. A bounded change may reconsider only affected design
decisions or retain the current architecture after proving that its technology,
trust, data, recovery, Region, and validation boundaries did not change. Every
omitted domain needs a current basis; uncertain impact uses full revalidation.
This changes work depth, not safety, owner questions, or the two-gate lifecycle.

Gate B also records a risk-derived Harness Profile. It selects the smallest
exact checks justified by the approved technology, risk, data, identity,
exposure, recovery, and AWS lane; it never imposes a universal scanner.

### Fastlane Semantic Contract profile

Reviewed 2026-07-28 against [Semantic Anchors](https://llm-coding.github.io/Semantic-Anchors/),
[Semantic Contracts](https://llm-coding.github.io/Semantic-Anchors/contracts/),
[spec-driven development](https://llm-coding.github.io/Semantic-Anchors/spec-driven-development/),
and the [Harness Inventory](https://llm-coding.github.io/Semantic-Anchors/harness-inventory/).
These are design vocabulary, not a package, runtime dependency, user workflow,
or additional authority. `ADOPT` means the named official contract is used as
written; `ADAPT` means Fastlane defines a narrower local contract;
`CONDITIONAL` activates only on its stated trigger; `NOT_APPLICABLE` means
Fastlane does not mandate the technique, although an approved project may.

| Profile ID | Local contract | Official basis | Disposition | Fastlane meaning | Authority | Activation trigger / exclusion | Deterministic validation or evidence | Owner-facing effect |
|---|---|---|---|---|---|---|---|---|
| FSC-001 | Single source of truth and meaningful human control | SSOT; Meaningful Human Control; Semantic Contracts | ADOPT | One authority per fact; owners approve consequential boundaries | `AGENTS.md`; canonical project records | Always | Engine state, receipt, and authority checks | Two understandable approvals |
| FSC-002 | Concise, plain-language progressive disclosure | Concise Response; BLUF; Plain English; Progressive Disclosure; Explaining and Teaching | ADAPT | Lead with status, needed action, and what follows; teaching is opt-in | Presenter, prompt pack, explain skill | Always; teaching only on request | Presenter and prompt-contract tests | Concise responses without ledger dumps |
| FSC-003 | Focused Socratic discovery and completeness | Requirements Discovery; Socratic Method; MECE | ADAPT | Ask at most three related questions and cover non-overlapping product concerns | REQ procedure and intake contract | Define | Procedural: coordinator reviews semantic overlap and completeness; Deterministic: card-size, provenance, seven-field foundation, journey, and requirement-projection checks | Short questions in ordinary language |
| FSC-004 | Outcome, actor, and first-release traceability | Specification; Actor-Goal List; Impact Mapping; User Story Mapping | ADAPT | Fastlane adopts outcome-to-actor-to-journey traceability but keeps fully dressed use cases and diagrams conditional under FSC-009; every first-release requirement maps to its owner-grounded outcome and canonical acceptance/test bindings | PRD requirements contract | Gate A readiness | Requirements-contract projection and inverse actor/journey coverage | Clear product agreement |
| FSC-005 | Observable normative requirements and acceptance | Specification; EARS; Gherkin; Quality Attribute Scenario | ADAPT | Normative requirements are observable and testable | PRD normative tables | Gate A; QAS only when material | Requirement and QAS validators | Requirements state what success means |
| FSC-006 | Whole-system choices, traceability, and layer boundaries | Strategic Architecture Analysis; Layer Boundaries; ADR | ADAPT | Compare viable systems, preserve explicit inward boundaries, and trace only to declared design and validation IDs | PRD design contract | New or materially changed architecture | Candidate, declared-ID traceability, example-scenario binding, boundary, and digest checks | One reasoned recommendation |
| FSC-007 | Bounded work and the first end-to-end outcome | INVEST; Vertical Slicing; Walking Skeleton; Thin Vertical Slice; Spike Solution | ADAPT | A new build starts with one tested usable path; a blocking spike is disposable | TASKS ledger and first-wave contract | TASK-10 for `NEW_BUILD` | Task graph, wave, and spike checks | Useful progress appears early |
| FSC-008 | Closed-loop construction and maintenance | Implement Next; Red/Green TDD; Property-Based Testing; Definition of Done; Refactoring; Mikado Method | ADAPT | Construction and maintenance iterate against exact checks and observed evidence | Harness, tasks, VERIFY, maintenance skill | When selected by risk, technology, or bounded repair | Procedural: coordinator selects and applies TDD, refactoring, or Mikado; Deterministic: Harness, property, task/DONE, and observed-evidence checks | Codex corrects safe in-scope failures |
| FSC-009 | Rich use cases and state machines; optional flow diagrams | Cockburn Use Cases; Activity Diagrams; State Machines | CONDITIONAL | Add rich guarantees to each triggering journey, and to every journey at high/critical risk; use Mermaid flow diagrams only as presentation aids | PRD journey and state contracts; optional diagrams are non-authoritative | High/critical risk; materially branching, async, retry/resume, approval, migration, permissioned, or meaningful-transition trigger | Per-journey rich-use-case and existing state applicability validators | Extra detail only when the flow demands it |
| FSC-010 | Threat, application-security, and privacy analysis | Quality Review; STRIDE; LINDDUN; OWASP Top 10 | CONDITIONAL | Threat/privacy analysis deepens material security work; applicable web, API, or application surfaces receive an OWASP Top 10 review | PRD security/privacy requirements, design trust boundaries, Harness, and VERIFY | Material security/privacy trigger or applicable web/API/application attack surface | Procedural: trigger review and STRIDE/LINDDUN/OWASP Top 10 application; Deterministic: resulting requirement, control, test, Harness, and evidence-ID traceability | Security depth matches exposure |
| FSC-011 | Consequential decision and review depth | Quality Review; ATAM; ADR; Fagan Inspection | CONDITIONAL | Hard-to-reverse choices receive deeper review | Current PRD decision; cited ADR rationale/history only | One-way door, high/critical risk, or material tradeoff | Procedural: trigger and ATAM/ADR/Fagan review; Deterministic: candidate, selection, traceability, and digest checks | Tradeoffs are visible when consequential |
| FSC-012 | Extended Harness checks | Harness Inventory | CONDITIONAL | Accessibility, visual, mutation, SAST/DAST, and formal checks activate from technology/risk | Gate B Harness Profile | Technology/risk applicability review | Procedural: applicability review; Deterministic: every recorded row's status, basis, exact command/API, evidence destination, and scope | No universal scanner burden |
| FSC-013 | External issue tracking | Backlog Management | CONDITIONAL | Mirror tasks only when authorized and operationally useful | TASKS and GitHub boundary | Current external-write authority | Issue reconciliation checks | No issue ceremony by default |
| FSC-014 | Repository-native Docs-as-Code and optional external documentation stack | Docs-as-Code; Architecture Documentation; arc42; AsciiDoc/docToolchain; PlantUML | ADAPT | Markdown documents and Mermaid diagrams are versioned, linked, validated authorities; arc42, AsciiDoc/docToolchain, and PlantUML are not mandatory | Fastlane package and documentation contracts | Always for repository-native docs; external stack only when a project constraint selects it | Manifest, relative-link, Markdown, Mermaid, and package integrity tests | Familiar repository documents without mandatory external tooling |
| FSC-015 | Extra lifecycle and approval machinery | Pugh Matrix; Backlog Management | NOT_APPLICABLE | No second lifecycle, extra gate, universal scoring, or issue-per-task execution | Workflow and receipt contracts | Excluded from Fastlane | Route and exact-receipt tests | No added approval bureaucracy |
| FSC-016 | Semantic Anchors package or runtime | Semantic Anchors; Semantic Contracts | NOT_APPLICABLE | The profile is locally defined and dependency-free | This table and local validators | Excluded from runtime/package | Manifest and package inventory checks | No additional installation |
| FSC-017 | Baseline threat/security boundary and crosscutting quality | Crosscutting Concepts | ADAPT | A lightweight threat surface plus security, testing, observability, and error handling are always addressed; formal STRIDE/LINDDUN/OWASP Top 10 depth remains conditional under FSC-010 | PRD security/privacy requirements and architecture trust boundaries; Harness; RUNBOOK; VERIFY | Always for the baseline; FSC-010 trigger for formal threat/privacy/application-security analysis | Requirement, design, Harness, runbook, and evidence validators | Safe operational defaults without extra lifecycle or approval ceremony |
| FSC-018 | Complete requirement-to-delivery disposition | Specification; Implement Next; Definition of Done | ADAPT | Every modern approved first-release requirement resolves to task coverage, current no-task proof, or evidence-backed optional non-applicability | PRD requirements contract, TASKS traces, and VERIFY evidence | TASK-10 and every `CURRENT` task-plan check | Engine derives exact requirement/acceptance dispositions and reports missing IDs | No approved requirement disappears and no extra owner gate is added |

## Framework maintenance

Fastlane framework work uses `maintain-fastlane`, never the adopter lifecycle.
It has four modes: `AUDIT` and `PLAN` are read-only; `IMPLEMENT` permits only
local edits inside a recorded baseline, outcome, non-goals, file allowlist,
acceptance criteria, and change budget; and `PUBLISH` requires separate exact
authority for each Git or release action. Missing implementation scope stops
before editing. Unrelated findings remain report-only, and publication never
follows merely from permission to edit.
A change to an FSC contract updates its workflow rule, applicable phase
reference, PRD schema, deterministic validator/router, owner-visible
presentation when affected, tests, and manifest in the same bounded
maintenance change.
Use `python scripts/maintenance_preflight.py --contract <contract.json> --root . --json`
to verify the exact baseline, allowlist, change budget, and distinct publication
authority before maintenance work. The contract is ephemeral and untracked.

For canonical customer-package maintenance, compare the current manifest
inventory and bytes with one exact existing ancestor using `python
scripts/package_release.py --check --base-commit <exact-base-commit>`. When the
package differs, `bootstrap.manifest.json` must contain a strictly greater
semantic version and its mirrors must match. The guard is read-only, never
fetches or publishes, and fails closed when the exact history is unavailable.
It does not require initialized adopter applications to change Fastlane's
framework version.

The live `fast-lane-maint` customer branch uses short-lived maintenance branches
and pull requests targeting only that customer branch. The PR branch must be
current before merge, and these checks must pass: `safety-tests (3.11)`,
`safety-tests (3.12)`, `safety-tests (3.13)`, `windows-smoke`, and
`macos-setup-smoke`. Force pushes and deletion of the customer branch are
prohibited. A direct push to `fast-lane-maint` requires explicit emergency
publication authorization; ordinary `PUBLISH` work uses the PR-gated flow.

GitHub branch-rule configuration is a separate repository-setting action. The
repository documents the required policy but does not treat source-edit,
commit, push, or PR authority as permission to change that setting. Protected
legacy `Legacy` is not a customer publication target.


## AWS Core throughout Fastlane

Fastlane requires the current official
`aws-core@agent-toolkit-for-aws` from `aws/agent-toolkit-for-aws` at the
material lifecycle points below whenever current AWS facts affect:

- feasibility and requirements;
- service and Region fit;
- architecture, IAM, networking, encryption, and data protection;
- reliability, quotas, observability, and cost drivers;
- release readiness, deployment, rollback, operations, and teardown.

Official AWS Core is a fresh-template prerequisite and is reused when already
available. After initialization, a genuinely unavailable capability is owner
setup. Missing, stale, or safely repairable generated evidence while that
capability is available is Codex work; unexplained structural drift or unsafe
evidence conflict requires human review. Each case pauses only the affected
material AWS step and never repeats completed setup or intake.
Fresh setup starts with exactly one credential-free `AWS skills`
`search_documentation` call followed by `retrieve_skill` for an identifier
returned by that search. Topic-specific AWS discovery begins later only for a
material Define, Design, or AWS-10 question; it does not repeat or replace the
completed setup chain.

REQ-10 classifies AWS Core materiality as `REQUIRED`, `OPTIONAL`, or
`NOT_MATERIAL`. `REQUIRED` applies when Gate A depends on a current AWS fact
about Region or service feasibility, identity, sensitive data or uploads,
public exposure, encryption, deletion or recovery, quotas, availability, or
material cost. The coordinator then records a fresh
`search_documentation`-then-matching-`retrieve_skill` chain against the current
REQ and affected requirement IDs without selecting architecture or accessing
an AWS account.

REQ-10 when required, DESIGN-10, and AWS-10 record fresh attributable
`search_documentation` and matching `retrieve_skill` results in
`docs/project/VERIFY.md`. A generic
connector, cached prose, or model memory does not satisfy required evidence.
AWS Core advises; it cannot approve Gate A, Gate B, or an AWS change.

## Gate A

Gate A approves one exact requirements revision. It includes users, outcomes,
scope, data, failure behavior, access, security, recovery, cost posture, and
measurable success. It does not approve design, construction, GitHub mutation,
AWS access, or spending.

## Gate B

Gate B approves the exact current PRD and a construction envelope naming the
outcome, scope, write boundaries, prohibited work, task and retry limits,
checkpoints, GitHub permission, and planned AWS lane.

After Gate B, Codex can build normally without repeated approvals. A material
change in requirements, design, scope, risk, cost, or authority makes the
applicable gate stale and stops affected work.
A task-coverage omission or trace mismatch by itself is generated-plan drift:
Codex replans and revalidates inside the unchanged Gate B boundary. Owner input
is required only when resolving the gap would change an approved requirement,
design decision, construction boundary, or authority.

### Legacy contract compatibility

Schema transitions do not create another owner gate. An unchanged approved schema 1.2 Gate A may be used as the requirements basis while Codex performs a design-only migration to schema 5. Codex writes generated migration records and reports `Need from you: Nothing` unless an owner fact required by the current requirements is genuinely missing. A requirements-controlled change instead requires schema 1.3 and makes the applicable approvals stale.

That bridge derives acceptance labels from approved legacy rows. A legacy
`NEW_BUILD` uses first-wave journey `NONE` and binds its end-to-end Harness to
the wave plus every selected approved requirement; it does not invent a journey.

An unchanged approved schema 4 Gate B remains valid for its exact design and construction envelope. A new or unapproved design, or any design-controlled change, requires the complete schema 5 design contract and a fresh Gate B. Legacy compatibility cannot expand authority, invent design values, or bypass task and evidence checks. The owner supplies a missing product fact when one is needed and approves the resulting Gate B; Codex owns the mechanical migration.

## AWS authorization

An AWS lane describes intended access; it never grants access. Documentation
guidance is credential-free and accesses no AWS account. Authenticated AWS-10
preflight requires a separate exact `AUTHORIZE AWS READ-ONLY PREFLIGHT`
receipt naming:

- profile or role, account, Region, and environment;
- immutable artifact, exact resources, and allowed read-only operations;
- expiration; and
- human approver.

That receipt grants no mutation. Fastlane then moves deterministically through
`AWS_GUIDANCE_REQUIRED`, `AWS_READ_SCOPE_REQUIRED`, `AWS_PREFLIGHT_RUNNING`,
and an observed `AWS_PREFLIGHT_READY`. Only after observed readiness may an
explicit-gate workflow enter `WAITING_AWS_MUTATION_AUTH` and present the exact
deployment receipt.

For a Gate B boundary that permits authenticated AWS work, `AWS allowed
operations` names the union of the exact read-only preflight/reconciliation
operations and any later mutation or teardown operations. This is one maximum
approved envelope, not authority to run every listed operation: AWS-10,
AWS-30, and AWS-40 remain read-only, while AWS-20 and AWS-50 still require
their own current phase evidence and action-specific authority.

Before an AWS-20 call, Fastlane appends a STARTED row to the canonical
append-only deployment action and reconciliation table. Every row keeps the
attempt's deployment authorization, validity, and stable source unchanged;
fast-dev stores the exact current construction `AUTH-*`, the expiry timestamp
parsed from Gate B validity, and Gate B's authorization source; explicit-gate
derives them from its deployment receipt.
The terminal result uses the canonical identifiers/result grammar, which
structures evidence but cannot prove execution alone. Fastlane then routes the
Attempt ID to AWS-30.
STARTED is not proof that a call occurred. If only STARTED exists on resume,
owner action remains NONE while Codex appends UNKNOWN and reruns the Engine;
only then may AWS-30 request read authority. FAILED, PARTIAL, or UNKNOWN cannot
be retried before read-only reconciliation. AWS-30 requires independently
current exact read authority; deployment authority cannot supply those reads,
carry over, or be replayed. While Gate B remains current, an exact matching
AWS-10 receipt may be reused if it is still current and covers reconciliation.
Restricted stale or expired closure instead requires fresh post-action read
authority. COMPLETE or BLOCKED returns to RELEASE-10, while
one first STALE remains at AWS-30 until its authority and evidence are current.
That STALE may be followed by one later COMPLETE or BLOCKED under a different
current read authorization. A repeated STALE is a safety-review blocker; no
reconciliation row follows COMPLETE or BLOCKED. RELEASE-10 records that
terminal AWS-30 Evidence ID as VERIFY's Active evidence cutoff when it decides
NOT_READY, RELEASE_VERIFIED, or a separately authorized correction path. Once
acknowledged, the attempt cannot reroute. Retry requires distinct current
mutation authority: a new exact deployment receipt for explicit-gate or freshly
approved construction authorization for fast-dev, plus a new Attempt ID.

Every AWS-30 row stores `Read authority source` exactly as `SOURCE: <stable
owner-message source>; AUTHORIZED_AT: <ISO 8601 with timezone>; RESOURCES:
<exact canonical list>; OPERATIONS: <exact canonical list>`. `AUTHORIZED_AT` is
the `Observed at` timestamp of the matching Read-only preflight row in Action
authorization provenance, not the owner-message creation time or the AWS-30
evidence-row observation time. The AWS observation stays within that
authorization window, Resources exactly match the encoded resource list, and
observed operations are a subset of the encoded allowed operations.
Current terminal evidence matches the current receipt tuple; an acknowledged
historical row remains auditable from its stored tuple after later expiry or
replacement.

Gate B expiry or legitimate REQ/DES/Gate B staleness after a valid STARTED row
does not abandon the attempted action and does not reauthorize normal work.
Fastlane keeps ordinary construction, repository-write, and AWS mutation
authority at NONE and exposes a separate
`deployment_journal_closure_authority`. That closure is limited to
`docs/project/VERIFY.md` and the Engine-selected bounded operation: append
UNKNOWN for a lone STARTED row; record the exact marked read receipt/provenance
and append its AWS-30 reconciliation row; or atomically update RELEASE-10's
release decision and Active evidence cutoff. BLOCKED permits only `NOT_READY`;
stale-basis COMPLETE permits only `NOT_READY`; same-basis COMPLETE permits
`NOT_READY` or `RELEASE_VERIFIED`. Only deployment journal rows are
append-only; receipt/provenance and release decisions use their canonical
update contracts. A fresh exact post-action read receipt may close the
immutable historical attempt boundary without renewing mutation authority.
The durable original deployment receipt/provenance must also prove that
STARTED did not precede its authorization. Only a structurally valid attempt
that STARTED while its authority was current qualifies; malformed or tampered receipts,
journal rows, timing, identities, boundaries, or evidence remain blockers. A
consumed attempt never gains closure authority merely because the release is
later marked READY_TO_DEPLOY; retry still needs fresh mutation authority and a
new Attempt ID. A consumed `NOT_READY` attempt stops at
`RELEASE_REVIEW_BLOCKED` unless the owner separately records a current
non-authorizing lifecycle intent. That intent may select AWS-40 read-only
residual review, but it never retries deployment or grants account access.

At a settled release boundary, the optional lifecycle-intent record contains
the value, source, and recorded-at time. A non-`NONE` value requires source
exactly `owner-message MSG-AWS-LIFECYCLE-nnnn` plus a timezone-aware ISO 8601
time. `NONE` requires both provenance fields to be `NONE`. The normal profile is
`NONE`, `RESIDUAL_REVIEW`, or `TEARDOWN`. After current
`READY_FOR_TEARDOWN` or `RESIDUALS_REMAIN` evidence, the choice profile is
`RETAIN`, `RESIDUAL_REVIEW`, or `TEARDOWN`, shown to the owner as RETAIN,
INVESTIGATE, or REMOVE. Follow the Engine's `aws_residual_disposition`
projection rather than inferring a route from the raw value. The three fields
change atomically and record the owner's requested follow-up route without
granting access or mutation:

- `NONE` stops the workflow;
- RETAIN stores `RETAIN`, ends at `AWS_RESIDUALS_RETAINED`, and explicitly warns
  that retained resources may continue to incur cost;
- INVESTIGATE stores `RESIDUAL_REVIEW` and requires separate current read
  authority before AWS-40; and
- REMOVE stores `TEARDOWN`; with current READY evidence it may present the exact
  teardown receipt, while after `RESIDUALS_REMAIN` it first refreshes AWS-40.
  AWS-50 always returns to AWS-40 for terminal reconciliation.

Every choice after `RESIDUALS_REMAIN` must be strictly newer than that row.
After `READY_FOR_TEARDOWN`, RETAIN and INVESTIGATE must be strictly newer. An
earlier owner-provenanced TEARDOWN may carry forward as REMOVE. New residual
evidence reopens the set-level choice. RETAIN without current READY or residual
evidence is invalid.

A valid AWS-50 STARTED row, its terminal result, required post-action review,
or an explicit AWS-40 safety blocker always outranks elective intent and cannot
be hidden by changing intent to `NONE`. Legacy projects without provenance are
accepted only when their effective intent is `NONE`. Before authenticated read
authority becomes current, the owner may atomically return the record to
`NONE`; no lifecycle-intent write can create AWS authority. Every concrete
AWS-40 row stores `Read authority source` exactly as `SOURCE: <stable
owner-message source>; AUTHORIZED_AT: <ISO 8601 with timezone>`.
`AUTHORIZED_AT` is the `Observed at` timestamp of the matching Read-only
preflight row in Action authorization provenance. Current observations stay
inside the receipt window and never exceed its resource/operation scope. Exact
scope equality applies only when the Engine requires exact-scope reconciliation;
STALE does not claim fresh reads. Later expiry or replacement does not invalidate
terminal evidence whose durable tuple was proven at append time.

AWS-50 records only the directly observed mutation attempt. All authenticated
pre- and post-teardown reads—including inventory, retention, operation
history, backups, residual resources, and continuing billing signals—belong to
AWS-40 under current read authority.

Every AWS mutation requires a separate current record naming:

- account, Region, and environment;
- allowed resources and operations;
- finite cost ceiling and billing dimensions;
- rollback or teardown plan; and
- expiration.

Tools, credentials, sandbox permission, prior access, or AWS Core availability
never replace either authorization. A read-only receipt cannot authorize
deployment or teardown, and a deployment receipt is not accepted as retroactive
read-scope authority.

## Measured context packets

The Engine resolves its compatibility selectors into exact, one-based inclusive
source ranges. It normalizes selected repository text to LF, ends it with one
LF, hashes those UTF-8 bytes, and reports the actual initial source-byte total
against the 12,000-byte source budget. This measures selected repository
content, not prompts, tool schemas, conversation history, tokens, or total model
context.

Required atomic lifecycle state is selected before non-atomic guidance.
Procedural guidance may move on demand even when high priority; lower-priority
material moves first when otherwise equivalent. One complete required record may
exceed the remaining budget and is reported honestly without creating an owner action; records are never truncated. Missing, ambiguous, or overlapping required source
fails closed through normal remediation. Packets are ephemeral and untracked.

## Fast-path expectations

A ready Quick MVP with a complete brief needs at most one clarification round
before Gate A. Setup questions occur once. Gate A continues into Design in the
same run; Design reaches pending Gate B without an owner pause unless a material
owner decision exists; Gate B continues into task generation in the same run.
Resume never repeats completed setup. Every paused or blocked response identifies
one next action; it asks the owner only for a genuine decision, setup step,
approval, authorization, protected-boundary decision, or human safety review.
Routine responses do not expose internal methodology, Harness, or context terms.
These expectations add no gate and never override an authority boundary.

The Engine classifies validation diagnostics individually. A safe Codex-owned
defect continues through correction and revalidation inside the current write
boundary and attempt budget. Manual-safety findings stop all automatic repair.
When safe Codex and owner findings coexist, Codex may repair only independent
agent-owned defects before rerunning the Engine and presenting the remaining
owner action. Unknown diagnostics fail closed to human review.

During framework maintenance, a stale manifest is regenerated only after the
read-only `maintain-fastlane` preflight proves every changed source is inside the
recorded allowlist. The application coordinator never infers that provenance.
Unexplained control-hash drift, unsafe paths, malformed manifest structure, and
protected-file changes always require human safety review.

## Optional hook guardrails

Fastlane requires no project hooks. Owners who want an additional native Codex
guardrail may manually review and enable the opt-in pack described in
[HOOKS.md](HOOKS.md). It adds read-only Fastlane Engine context, uses Engine-derived write and external boundaries to deny only clearly unauthorized external or out-of-scope file actions, preserves normal approval
prompts, runs bounded validation, and follows the Engine's automatic-
continuation result.

Hooks never approve a gate or external action. The Fastlane receipts,
construction envelope, AWS authorization, sandbox, and owner approvals remain
authoritative.

## Maintainer field qualification

Before claiming real AWS deployment readiness, maintainers follow the
[AWS Core field-qualification policy](EVALUATION.md#aws-core-field-qualification).
Codex selects the smallest disposable scenario using current AWS Core guidance,
then performs and evaluates it. AWS Core supplies current AWS knowledge,
decision guidance, procedures, and execution tools; Fastlane applies its
existing state, gates, authority, rollback, teardown, and evidence contracts.
The owner authorizes; IAM enforces; observed evidence proves what occurred.
AWS Core does not choose the product architecture or grant authority. This adds
no customer setup step, scorer, lifecycle stage, gate, or routine owner action.

## Resume behavior

The Engine selects the next prompt. Fresh templates require current official
AWS Core before initialization. Initialized projects skip that prerequisite
during normal resume; missing or stale AWS Core evidence later pauses only the
affected material AWS step. The Engine assigns unavailable capability to owner
setup, safely repairable generated evidence to Codex, and unexplained unsafe
structure to human review. Follow that derived remediation action, rerun the
Engine, and resume the selected route.

Maintainers can run the optional, credential-free-to-validate
[model role-play review](EVALUATION.md) before a release. Its schema-4 manifest
binds external transcript, scorecard, and adjudication files to the exact
commit and prompt contract. A passing scorer result proves only exported
evidence integrity and score consistency; it never claims release readiness.
Live model access is never part of ordinary CI.
