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

1. project name;
2. preferred AWS Region; and
3. development budget posture.

Use a finite cap with currency when one exists, or answer
`minimize cost; no hard cap`. Codex initializes the project, runs the doctor,
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
| BOOT-00 | Repository initialized or safely resumed | None |
| INTAKE-10 / REQ-10 | Requirements, assumptions, cost posture, safeguards, and success criteria | Answer questions |
| Gate A / INTAKE-20 | Exact requirements revision reviewed | Approve requirements for design |
| DESIGN-10 | Technical PRD, current AWS evidence, and construction envelope | None until ready |
| Gate B / DESIGN-20 | Exact design and construction boundary reviewed | Approve construction |
| TASK-10 / BUILD | Dependency-aware tasks run inside the approved boundary | No task-by-task approval |
| RELEASE-10 | Release evidence evaluated | Only when the release contract requires it |
| AWS-10 | Read-only deployment preflight | No mutation authority |
| AWS-20 / AWS-50 | Exact authorized deployment or teardown | Separate expiring AWS authorization |
| AWS-30 / AWS-40 | Deployed evidence and residual review | Governed by the authorization and runbook |

Gate A — approve requirements → Gate B — approve the PRD and construction boundary → Codex builds autonomously inside that boundary.
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
or additional authority. `NOT_APPLICABLE` means Fastlane does not mandate the
technique; a project may still select it when approved technology or risk warrants it.

| Profile ID | Local contract | Official basis | Disposition | Fastlane meaning | Authority | Activation trigger / exclusion | Deterministic validation or evidence | Owner-facing effect |
|---|---|---|---|---|---|---|---|---|
| FSC-001 | Single source of truth and meaningful human control | SSOT; Meaningful Human Control; Semantic Contracts | ADOPT | One authority per fact; owners approve consequential boundaries | `AGENTS.md`; canonical project records | Always | Engine state, receipt, and authority checks | Two understandable approvals |
| FSC-002 | Concise, plain-language progressive disclosure | Concise Response; BLUF; Plain English; Progressive Disclosure; Explaining and Teaching | ADAPT | Lead with status, needed action, and what follows; teaching is opt-in | Presenter, prompt pack, explain skill | Always; teaching only on request | Presenter and prompt-contract tests | Concise responses without ledger dumps |
| FSC-003 | Focused Socratic discovery and completeness | Requirements Discovery; Socratic Method; MECE | ADAPT | Ask at most three related questions and cover non-overlapping product concerns | REQ procedure and intake contract | Define | Intake parser, foundation, and journey checks | Short questions in ordinary language |
| FSC-004 | Outcome, actor, and first-release traceability | Specification; Actor-Goal List; Impact Mapping; User Story Mapping | ADOPT | Every first-release requirement maps to its owner-grounded outcome | PRD requirements contract | Gate A readiness | Requirements-contract projection | Clear product agreement |
| FSC-005 | Observable normative requirements and acceptance | Specification; EARS; Gherkin; Quality Attribute Scenario | ADAPT | Normative requirements are observable and testable | PRD normative tables | Gate A; QAS only when material | Requirement and QAS validators | Requirements state what success means |
| FSC-006 | Whole-system choices, traceability, and layer boundaries | Strategic Architecture Analysis; Layer Boundaries; ADR | ADAPT | Compare viable systems and preserve explicit inward boundaries | PRD design contract | New or materially changed architecture | Candidate, boundary, traceability, and digest checks | One reasoned recommendation |
| FSC-007 | Bounded work and the first end-to-end outcome | INVEST; Vertical Slicing; Walking Skeleton; Thin Vertical Slice; Spike Solution | ADAPT | A new build starts with one tested usable path; a blocking spike is disposable | TASKS ledger and first-wave contract | TASK-10 for `NEW_BUILD` | Task graph, wave, and spike checks | Useful progress appears early |
| FSC-008 | Closed-loop construction and maintenance | Implement Next; Red/Green TDD; Property-Based Testing; Definition of Done; Refactoring; Mikado Method | ADAPT | Construction and maintenance iterate against exact checks and observed evidence | Harness, tasks, VERIFY, maintenance skill | When selected by risk, technology, or bounded repair | Harness/task/evidence validators | Codex corrects safe in-scope failures |
| FSC-009 | Rich use cases and state machines | Cockburn Use Cases; State Machines | CONDITIONAL | Add failure guarantees or states only when triggered | PRD journey and state contracts | High/critical risk; lifecycle, async, retry/resume, approval, migration, or meaningful-transition trigger | Applicability and record validators | Extra questions only when risk demands them |
| FSC-010 | Threat and privacy analysis | Quality Review; STRIDE; LINDDUN | CONDITIONAL | Threat and privacy analysis deepen material security work | PRD design and risk records | Material security/privacy trigger | Recorded trigger plus bound findings and validation IDs | Security depth matches exposure |
| FSC-011 | Consequential decision and review depth | Quality Review; ATAM; ADR; Fagan Inspection | CONDITIONAL | Hard-to-reverse choices receive deeper review | PRD and `docs/adr/` | One-way door, high/critical risk, or material tradeoff | Recorded trigger plus decision/evidence review | Tradeoffs are visible when consequential |
| FSC-012 | Extended Harness checks | Harness Inventory | CONDITIONAL | Accessibility, visual, mutation, SAST/DAST, and formal checks activate from technology/risk | Gate B Harness Profile | Recorded trigger | Exact command/API and evidence row | No universal scanner burden |
| FSC-013 | External issue tracking | Backlog Management | CONDITIONAL | Mirror tasks only when authorized and operationally useful | TASKS and GitHub boundary | Current external-write authority | Issue reconciliation checks | No issue ceremony by default |
| FSC-014 | Mandatory external documentation stack | Architecture Documentation; Docs-as-Code; arc42; AsciiDoc/docToolchain; PlantUML | NOT_APPLICABLE | Repository-native Markdown/Mermaid authorities remain canonical | Fastlane package contract | External stack excluded as mandatory machinery | Manifest and Markdown integrity tests | Familiar repository documents |
| FSC-015 | Extra lifecycle and approval machinery | Pugh Matrix; Backlog Management | NOT_APPLICABLE | No second lifecycle, extra gate, universal scoring, or issue-per-task execution | Workflow and receipt contracts | Excluded from Fastlane | Route and exact-receipt tests | No added approval bureaucracy |
| FSC-016 | Semantic Anchors package or runtime | Semantic Anchors; Semantic Contracts | NOT_APPLICABLE | The profile is locally defined and dependency-free | This table and local validators | Excluded from runtime/package | Manifest and package inventory checks | No additional installation |

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

Fastlane prefers the current official
`aws-core@agent-toolkit-for-aws` from `aws/agent-toolkit-for-aws` whenever
current AWS facts materially affect:

- feasibility and requirements;
- service and Region fit;
- architecture, IAM, networking, encryption, and data protection;
- reliability, quotas, observability, and cost drivers;
- release readiness, deployment, rollback, operations, and teardown.

Official AWS Core is a fresh-template prerequisite and is reused when already
available. After initialization, missing or stale AWS Core evidence pauses only
the affected material AWS step and never repeats completed setup or intake.
Fresh setup starts with exactly one credential-free `AWS skills`
`search_documentation` call followed by `retrieve_skill` for an identifier
returned by that search. Topic-specific AWS discovery begins later only for a
material Define, Design, or AWS-10 question; it does not repeat or replace the
completed setup chain.

DESIGN-10 and AWS-10 record fresh attributable `retrieve_skill` and
`search_documentation` results in `docs/project/VERIFY.md`. A generic
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

### Legacy contract compatibility

Schema transitions do not create another owner gate. An unchanged approved schema 1.2 Gate A may be used as the requirements basis while Codex performs a design-only migration to schema 5. Codex writes generated migration records and reports `Need from you: Nothing` unless an owner fact required by the current requirements is genuinely missing. A requirements-controlled change instead requires schema 1.3 and makes the applicable approvals stale.

That bridge derives acceptance labels from approved legacy rows. A legacy
`NEW_BUILD` uses first-wave journey `NONE` and binds its end-to-end Harness to
the wave plus every selected approved requirement; it does not invent a journey.

An unchanged approved schema 4 Gate B remains valid for its exact design and construction envelope. A new or unapproved design, or any design-controlled change, requires the complete schema 5 design contract and a fresh Gate B. Legacy compatibility cannot expand authority, invent design values, or bypass task and evidence checks. The owner supplies a missing product fact when one is needed and approves the resulting Gate B; Codex owns the mechanical migration.

## AWS authorization

An AWS lane describes intended access; it never grants access. Every AWS
mutation requires a separate current record naming:

- account, Region, and environment;
- allowed resources and operations;
- finite cost ceiling and billing dimensions;
- rollback or teardown plan; and
- expiration.

Tools, credentials, sandbox permission, prior access, or AWS Core availability
never replace this authorization.

## Measured context packets

The doctor resolves its compatibility selectors into exact, one-based inclusive
source ranges. It normalizes selected repository text to LF, ends it with one
LF, hashes those UTF-8 bytes, and reports the actual initial source-byte total
against the 12,000-byte source budget. This measures selected repository
content, not prompts, tool schemas, conversation history, tokens, or total model
context.

Lower-priority material moves on demand. One complete required record may exceed
the remaining budget and is reported honestly without creating an owner action;
records are never truncated. Missing, ambiguous, or overlapping required source
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

The doctor classifies validation diagnostics individually. A safe Codex-owned
defect continues through correction and revalidation inside the current write
boundary and attempt budget. Manual-safety findings stop all automatic repair.
When safe Codex and owner findings coexist, Codex may repair only independent
agent-owned defects before rerunning the doctor and presenting the remaining
owner action. Unknown diagnostics fail closed to human review.

During framework maintenance, a stale manifest is regenerated only after the
read-only `maintain-fastlane` preflight proves every changed source is inside the
recorded allowlist. The application coordinator never infers that provenance.
Unexplained control-hash drift, unsafe paths, malformed manifest structure, and
protected-file changes always require human safety review.

## Optional hook guardrails

Fastlane requires no project hooks. Owners who want an additional native Codex
guardrail may manually review and enable the opt-in pack described in
[HOOKS.md](HOOKS.md). It adds read-only doctor context, uses doctor-derived write and external boundaries to deny only clearly unauthorized external or out-of-scope file actions, preserves normal approval
prompts, runs bounded validation, and follows the doctor's automatic-
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

The doctor selects the next prompt. Fresh templates require current official
AWS Core before initialization. Initialized projects skip that prerequisite
during normal resume; missing or stale AWS Core evidence later pauses only the
affected material AWS step. Follow the derived remediation action, rerun the
doctor, and resume the selected route.

Maintainers can run the optional, credential-free-to-validate
[model role-play review](EVALUATION.md) before a release. Its schema-4 manifest
binds external transcript, scorecard, and adjudication files to the exact
commit and prompt contract. A passing scorer result proves only exported
evidence integrity and score consistency; it never claims release readiness.
Live model access is never part of ordinary CI.
