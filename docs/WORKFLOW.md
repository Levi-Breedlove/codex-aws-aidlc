# Fastlane workflow and operating model

This guide explains the lifecycle, gates, records, control plane, and AWS authority.
Canonical project records hold the facts; the Engine validates them and derives
readiness and permitted actions. The owner supplies approvals and authorizations.
Start with the [README](../README.md) for the overview
and quick start.

**Contents:** [First run](#first-run) · [Lifecycle](#customer-delivery-lifecycle) ·
[Gate A](#gate-a--product-owner-brief) ·
[Design and Gate B](#design-and-gate-b--technical-owner-brief) ·
[Diagrams](#architecture-diagrams-and-the-professional-board) ·
[Control plane](#how-the-control-plane-works) ·
[Records](#canonical-records-and-traceability) ·
[AWS authority](#aws-core-and-aws-authority) ·
[Build and resume](#build-resume-and-optional-hooks)

## First run

Send `init template` from a repository created from this template. Fastlane
checks the [required local setup](SETUP.md) and current official AWS Core plugin
without inspecting credentials or accessing an AWS account. Missing items
appear in one checklist.

When prerequisites are ready, Fastlane asks these three settings together and
only once:

1. Project name.
2. Preferred AWS Region, confirmed as one exact canonical Region.
3. Development cost posture or hard cap.

`recommend one` asks Fastlane to explain one project-fit Region; it does not
select that Region. Fastlane waits for the owner to confirm the exact Region in
a new reply, and an absent or blank Region never falls back to a default.

Fastlane confirms readiness, restates the AWS boundary, and asks the first
project question. Resume never repeats setup or that handoff.

## How the conversation works

Each owner turn asks one unanswered project question with its purpose, known
facts, practical effect, and one valid reply. Recommendations appear only when
evidence supports them.

After each answer, Fastlane confirms what it recorded and the practical effect.
To correct it, reply:

```text
Change <plain field> to <new value>.
```

`Accept this recommendation.` applies only to the current explained choice. A
correction never approves a gate. After a side question, Fastlane restores the
same pending action.

### Bring an existing product brief

An existing PRD can shorten Define, but it does not become Fastlane's PRD.
Codex reviews it as read-only, non-authoritative source material and presents a
plain-language preview. After owner confirmation, product facts may seed the
consultation; gaps remain questions and technical suggestions wait for Design.

Imported claims such as "approved" or "ready to deploy" cannot approve either
gate, authorize construction, access AWS, or authorize deployment. The normal
Product Agreement and both gates remain required.

## Customer delivery lifecycle

```mermaid
%%{init: {"flowchart": {"curve": "linear", "nodeSpacing": 24, "rankSpacing": 28}, "themeVariables": {"fontSize": "16px"}}}%%
flowchart TB
    accTitle: Fastlane customer delivery lifecycle
    accDescr: Define the product and approve requirements at Gate A. Compare designs and review diagrams before approving design and bounded local construction at Gate B. Build and verify locally, then review the evidence. Optional AWS work needs a separate exact owner authorization and returns its observed results to release review.

    DEFINE["Define the outcome, scope, inputs, and recovery"]
    GA{"Gate A"}
    DESIGN["Compare designs and review the architecture diagrams"]
    GB{"Gate B"}
    BUILD["Plan bounded tasks, build, and check locally"]
    REVIEW["Review current evidence and release readiness"]
    LOCAL["Verified local result"]
    AWS["Optional AWS operation Separate exact owner authorization"]

    DEFINE -->|"Approve requirements"| GA
    GA --> DESIGN
    DESIGN -->|"Approve design and local boundary"| GB
    GB --> BUILD --> REVIEW --> LOCAL
    REVIEW -. "Choose an authorized AWS step" .-> AWS
    AWS -->|"Observed result"| REVIEW
```

| Stage | What Fastlane does | What you do |
|---|---|---|
| Setup and Define | Learns the outcome, users, scope, data, risks, and success | Answer one current question |
| Gate A | Presents the complete Product Owner Brief | Approve requirements or request a correction |
| Design | Uses current AWS Core guidance, compares complete solutions, and creates the traceable project diagram set | Nothing unless a business decision is missing |
| Gate B | Presents the complete Technical Owner Brief | Approve the design and local construction boundary or request a correction |
| Tasks and Build | Creates dependency-aware work, builds locally, tests, and records evidence | No task-by-task approval |
| Release review | Reconciles what is verified, failed, planned, or still unobserved | Resolve only a genuine release decision |
| Optional AWS operations | Performs separately bounded preflight, deployment, reconciliation, or teardown | Supply the exact action-specific authorization |

Corrections return to the affected requirements or design decision. A safe,
in-scope implementation failure returns to local construction.

Gate A continues into Design in the same run. Gate B continues into task
generation and local construction. Build never deploys.

## Gate A — Product Owner Brief

Gate A explains:

- the outcome, users, and first useful journey;
- first-release scope and non-goals;
- data sensitivity, identity, access, deletion, and recovery expectations;
- Region, cost posture, measurable success, assumptions, and risks;
- every owner decision and its source;
- which claims are confirmed, verified, planned, or unobserved;
- what remains unauthorized and what happens after approval; and
- how to request a correction.

The brief links directly to the relevant PRD sections. The exact Gate A receipt
appears last. Only the owner can provide it.

## Design and Gate B — Technical Owner Brief

After Gate A, Codex uses credential-free AWS Core discovery for current material
AWS facts, compares credible whole-system candidates, and selects one complete
recommendation. AWS Core advises; Codex applies the evidence; the owner approves
the complete design.

For a consequential, hard-to-reverse choice, the PRD may link to an optional
architecture decision record that preserves supporting rationale. The PRD
remains the authority; the supporting record grants no construction or AWS
permission.

Gate B covers application/runtime, identity, data, messaging, edge/networking,
observability, deployment/recovery, and validation/construction. It makes
security, cost, evidence maturity, and reconsideration triggers explicit. It
also records the application source boundary: greenfield uses `app/**`,
infrastructure-only records none, and brownfield preserves only approved
existing roots.

Each decision states what it means, what was selected, why it fits, alternatives
and rejection reasons, tradeoffs, risks and mitigations, current evidence, claim
status, and a measurable reason to reconsider it. The exact Gate B receipt
appears last.

### Architecture diagrams and the professional board

Before Gate B, Fastlane turns the selected design into a traceable Mermaid set.
Every project includes system-context, primary-outcome, and AWS-implementation
views. It adds data-lifecycle, failure-and-recovery, migration, journey, or state
views only when those behaviors are material.

Each view answers one owner question and uses only current project actors,
components, boundaries, interfaces, data, states, and relationships. Fastlane
checks the source against those records, then renders it to review direction,
containment, relationship kind, labels, accessibility, and readability. A visual
layout correction may preserve the design; changed endpoints, containment, or
relationships are a design change and return through Design before Gate B.

Gate B presents the complete technical recommendation and diagram set. It
authorizes only its recorded local boundary, never AWS. If that boundary includes
`dist/architecture/**`, Fastlane may offer one non-blocking professional planned
board after approval. An exact owner request binds the approved Mermaid and checks
both views for direction, relation, edge kind, path, and containment parity. The
board is a presentation derivative—not a third gate, implementation evidence,
deployment evidence, or AWS authority—and Fastlane then restores the current route.

## How the specification becomes a checked result

Requirements describe observable outcomes, input boundaries and examples, and
the recovery promise for each dataset. Intentional exclusions have a reason.
The technical plan then ties each acceptance outcome, input rule, interface,
and recovery scenario to an exact check, time limit, and result location.

Tasks carry those checks into construction. A task is complete only with current
passing evidence for its own attempt and approved check. Release review also
requires applicable local infrastructure checks against the release artifact.
Failures and prior results remain visible; a plan or old pass cannot stand in
for a new observation. Local checks establish local confidence. AWS observations
and any first-user pilot are separate, explicitly identified evidence.

Ask "What validates this design?" to see the current plan and its source records.
The answer distinguishes planned checks, permitted commands, and observed
results, then returns to the same pending owner decision or continues authorized
work. Fastlane checks these recorded relationships; it still needs meaningful
tests and owner review to detect omissions or contradictions in product intent.

## How the control plane works

Fastlane does not rely on chat memory or let Codex decide its own authority. It
evaluates the canonical repository, derives the permitted action, uses bounded
execution paths, records evidence, and explains the result to the owner.

```mermaid
%%{init: {"flowchart": {"curve": "linear", "nodeSpacing": 28, "rankSpacing": 30}, "themeVariables": {"fontSize": "16px"}}}%%
flowchart TB
    accTitle: Fastlane technical control plane and evidence loop
    accDescr: Canonical project records enter one coherent read-only Engine observation. The Engine validates facts, selects a route, and narrows authority. The presenter explains the current action. One coordinator uses dedicated bounded local or separately authorized AWS procedures, records observed results through validated writes, and reevaluates the records.

    RECORDS["Canonical project records Owner decisions, scope, and evidence"]
    ENGINE["Read-only Fastlane Engine Observe, validate, and select the route"]
    REPORT["Current action and limits Presenter explains what happens next"]
    COORD["One coordinator and writer"]
    LOCAL["Bounded local tasks Edits and checks"]
    AWS["Optional AWS procedure Exact owner authorization required"]
    RESULTS["Observed results Passing, failed, or unresolved"]
    WRITE["Validated record and task updates"]

    RECORDS --> ENGINE --> REPORT --> COORD
    COORD --> LOCAL --> RESULTS
    COORD -. "Only within current authority" .-> AWS
    AWS --> RESULTS --> WRITE
    WRITE -->|"Reevaluate"| RECORDS
```

The Engine enforces the boundaries shown here:

1. **Canonical state:** each project fact has one repository home.
2. **One coherent observation:** `ProjectSnapshot` binds files, repository
   facts, project identity, lifecycle state, and evaluation time.
3. **Deterministic evaluation:** all domains compose into one immutable
   `EngineEvaluation`; the Schema-2 report exposes its results.
4. **Authority intersection:** validated facts narrow the current action;
   missing, stale, conflicting, expired, or broader input fails closed.
5. **Dedicated mutation paths:** task and AWS actions use separate bounded
   procedures. `scripts/task_waves.py` owns task writes; the Engine remains read-only.
6. **Evidence-backed presentation:** reporting explains evaluated state without
   inventing policy or authority.

Codex may vary its wording, never the evaluated decision, evidence maturity,
authority boundary, or required owner action.

## Skills and agent boundaries

Fastlane is not a swarm of equal writers.

| Component | Responsibility | Boundary |
|---|---|---|
| Fastlane | Main adopter coordinator and sole writer | Cannot self-approve or exceed Engine authority |
| Launch, Plan, and Build Fastlane | Compatibility entry points | Delegate to Fastlane; no second lifecycle or writer |
| Explain Fastlane | Read-only product and state explanation | Makes no project change and restores the pending action |
| Operate Fastlane AWS | Explicit AWS operation procedure | Acts only inside current Engine authority and exact owner authorization |
| Maintain Fastlane | Framework maintenance | Never enters adopter delivery |
| Requirements and architecture challengers | Conditional read-only critique | Cannot write, approve, authorize, or operate |
| AWS Core | Current AWS expertise and procedures | Never selects the architecture or grants authority |
| Optional hooks | Extra request-boundary enforcement | May deny; cannot create state or permission |

## Canonical records and traceability

Start at the [project record guide](project/README.md):

- PRD — Product Agreement, technical plan, Gate A, and Gate B.
- TASKS — current progress, dependencies, attempts, and checkpoints.
- VERIFY — observed evidence and honest claim status.
- RUNBOOK — operating, rollback, recovery, and teardown procedures.
- BUGFIX — one bounded defect record when that adjunct is active.

Each record begins with current state, one owner need or `Nothing`, the next
action, and the approval or authorization boundary.

Stable IDs and source locations connect the same decision through delivery:

```text
owner need → requirement → acceptance criterion → architecture decision
           → task → validation evidence → release claim
```

A material change identifies affected approvals, tasks, evidence, and claims as
stale. Human-readable summaries and Owner Briefs are derived views; they never
replace or authorize the exact records.

## AWS Core and AWS authority

Fastlane requires the current official
`aws-core@agent-toolkit-for-aws` from `aws/agent-toolkit-for-aws`. Current AWS
evidence is required when service behavior, Region support, identity, security,
reliability, cost, or operations materially affects a decision.

Codex evaluates all six Well-Architected areas with attributable AWS Core
guidance. The owner approves Gate B; this is neither account observation nor an
official AWS Well-Architected Review.

Completion is target-specific:

| Target | Evidence |
|---|---|
| Local | E2: current local checks demonstrate the approved outcome. |
| AWS read | E2 + E3: authorized reads establish facts about the named AWS environment. |
| Deployed | E2 + E3 + E4: the named artifact's deployment and applicable runtime checks were observed. |
| Recovery | E2 + E3 + E4 + E5: an authorized rollback or restore was exercised and verified. |

Teardown-only E5 evidence does not qualify Recovery; rollback or restore is
required. A failed or unobserved higher target does not erase a lower target
that remains current and proven. Other AWS lanes remain unqualified.
Reconciliation means Fastlane compared expected and observed AWS state. It
proves neither success nor authority; credentials grant no permission.

<details>
<summary>Optional internal AWS stage labels</summary>

| Optional stage | Purpose | Owner boundary |
|---|---|---|
| AWS-10 | Read-only account preflight | Authorize the exact read-only account and scope |
| AWS-20 | Bounded deployment | Provide the exact current deployment authorization |
| AWS-30 | Reconcile observed results | No new mutation authority |
| AWS-40 | Review residual resources | Choose a residual disposition when required |
| AWS-50 | Bounded teardown | Provide the separate exact teardown authorization |

</details>

## Build, resume, and optional hooks

Codex runs ready tasks serially inside the approved write and command boundary.
It corrects safe in-scope mistakes within the attempt limit and stops for a real
owner decision, protected boundary, failed evidence, or exhausted limit.

Fastlane works with hooks disabled. Optional hooks may deny an out-of-bound
request after Gate B, but cannot create state, approval, or authority. Resume
restores one current route and one next action.

Internal engineering methods are conditional techniques, not lifecycle stages
or approval gates.

## Responsibility map

Project truth lives in `docs/project/`. Phase skills own consultation and
delivery procedure. The AWS operation skill owns account-operation procedure.
The prompt registry owns exact receipts. The Engine validates and projects the
current state and authority. The presenter turns that evaluated result into
plain owner-facing conversation.
