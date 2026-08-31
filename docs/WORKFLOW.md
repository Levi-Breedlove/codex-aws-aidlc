# Fastlane workflow and operating model

This guide owns the lifecycle, gates, records, control plane, and AWS authority.
Start with the [README](../README.md) for the overview
and quick start.

**Contents:** [First run](#first-run) · [Lifecycle](#customer-delivery-lifecycle) ·
[Gate A](#gate-a--product-owner-brief) ·
[Design and Gate B](#design-and-gate-b--technical-owner-brief) ·
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
flowchart TB
    accTitle: Fastlane customer delivery lifecycle
    accDescr: The owner approves product and technical boundaries. Fastlane plans, builds, and verifies locally; corrections return to the affected stage, and separately authorized AWS results return to release review.

    IDEA["Describe the outcome or bounded change"]
    DEFINE["Define users, journeys, scope, data, risks, and success"]
    GATEA{"Gate A: approve the Product Agreement?"}
    DESIGN["Compare AWS-informed system designs"]
    GATEB{"Gate B: approve the plan and local boundary?"}
    TASKS["Create dependency-aware bounded tasks"]
    BUILD["Build inside approved local paths"]
    VERIFY["Run validation and classify evidence"]
    RELEASE{"Review release readiness"}
    LOCAL["Conclude with the verified local state"]
    AWSAUTH{"Authorize one exact AWS operation?"}
    AWSOPS["Preflight, deploy, reconcile, review, or teardown"]
    AWSRESULT["Record the observed AWS result"]

    IDEA --> DEFINE --> GATEA
    GATEA -->|"Approve"| DESIGN
    GATEA -. "Request changes" .-> DEFINE

    DESIGN --> GATEB
    GATEB -->|"Approve"| TASKS
    GATEB -. "Request changes" .-> DESIGN

    TASKS --> BUILD --> VERIFY --> RELEASE
    VERIFY -->|"Safe in-scope defect"| BUILD
    VERIFY -. "Material product gap" .-> DEFINE
    VERIFY -. "Material design gap" .-> DESIGN

    RELEASE -->|"Local result"| LOCAL
    RELEASE -. "Optional AWS path" .-> AWSAUTH
    AWSAUTH -->|"Exact scope only"| AWSOPS --> AWSRESULT --> RELEASE
```

| Stage | What Fastlane does | What you do |
|---|---|---|
| Setup and Define | Learns the outcome, users, scope, data, risks, and success | Answer one current question |
| Gate A | Presents the complete Product Owner Brief | Approve requirements or request a correction |
| Design | Uses current AWS Core guidance, compares complete solutions, and binds environment and dependency controls | Nothing unless a business decision is missing |
| Gate B | Presents the complete Technical Owner Brief | Approve the design and local construction boundary or request a correction |
| Tasks and Build | Creates dependency-aware work, builds locally, tests, and records evidence | No task-by-task approval |
| Release review | Reconciles what is verified, failed, planned, or still unobserved | Resolve only a genuine release decision |
| Optional AWS operations | Performs separately bounded preflight, deployment, reconciliation, or teardown | Supply the exact action-specific authorization |

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

Gate B authorizes only its recorded local boundary, never AWS. If it includes
`dist/architecture/**`, Fastlane may offer one non-blocking planned board. The
brief shows `Current AWS authority: NONE — planned maximum only`. An exact
request binds approved Mermaid, checks both views for direction, relation, edge
kind, path, and containment parity, and derives schema 2; it grants no gate or
AWS authority.

## How the control plane works

Fastlane does not rely on chat memory or let Codex decide its own authority. It
evaluates the canonical repository, derives the permitted action, uses bounded
execution paths, records evidence, and explains the result to the owner.

```mermaid
flowchart TB
    accTitle: Fastlane technical control plane and evidence loop
    accDescr: One coordinator evaluates canonical repository state through a read-only Engine, invokes only bounded action paths, and returns every observed result for canonical recording and reevaluation.

    OWNER["Owner: intent, decisions, gates, and exact receipts"]
    COORD["Fastlane: consultant, coordinator, and sole adopter writer"]
    PRESENTER["Presenter: evaluated status and one current action"]
    ALIASES["Launch, Plan, and Build compatibility aliases"]
    CRITICS["Read-only requirements and architecture challengers"]
    AWSCORE["AWS Core: current guidance and procedures"]
    HOOKS["Optional hooks: additional denial only"]

    subgraph STATE["Canonical repository state"]
        RECORDS["PRD · TASKS · VERIFY · RUNBOOK · BUGFIX"]
    end

    subgraph ENGINE["Read-only deterministic Fastlane Engine"]
        SNAP["ProjectSnapshot: one coherent observation"]
        EVAL["EngineEvaluation: Package · Define · Design · Deliver · AWS"]
        AUTH["Authority intersection, route, remediation, and context"]
        REPORT["Schema-2 report without new policy"]

        SNAP --> EVAL --> AUTH --> REPORT
    end

    subgraph PATHS["Dedicated bounded action paths"]
        WRITES["Validated canonical-record writes"]
        TASKSTATE["task_waves.py task-state mutation"]
        LOCAL["Approved application and infrastructure edits"]
        CHECKS["Harness and local evidence"]
        OPERATE["Operate Fastlane AWS"]
        ACCOUNT["Bounded AWS account action"]
        RESULTS["Observed local and AWS results"]
    end

    OWNER --> COORD
    ALIASES -. "Delegate" .-> COORD
    CRITICS -. "Critique" .-> COORD
    AWSCORE -. "Advise" .-> COORD

    RECORDS --> SNAP
    COORD -->|"Invoke evaluation"| SNAP
    REPORT -->|"Return route and bounded authority"| COORD
    COORD -->|"Render evaluated truth"| PRESENTER --> OWNER

    COORD -->|"Validated record update"| WRITES --> RECORDS
    COORD -->|"Approved task transition"| TASKSTATE --> RECORDS
    COORD -->|"Approved local edit"| LOCAL --> CHECKS --> RESULTS
    COORD -->|"Engine-authorized AWS request"| OPERATE --> ACCOUNT --> RESULTS

    AWSCORE -. "Supply current procedures" .-> OPERATE
    HOOKS -. "May deny" .-> LOCAL
    HOOKS -. "May deny" .-> OPERATE
    RESULTS -->|"Return for canonical evidence recording"| COORD
```

The diagram enforces six boundaries:

1. **Canonical state:** each project fact has one repository home.
2. **One coherent observation:** `ProjectSnapshot` binds files, repository
   facts, project identity, lifecycle state, and evaluation time.
3. **Deterministic evaluation:** all domains compose into one immutable
   `EngineEvaluation`.
4. **Authority by intersection:** validated facts narrow the current action;
   missing, stale, conflicting, expired, or broader input fails closed.
5. **Dedicated mutation paths:** task and AWS actions use separate bounded
   procedures while the Engine remains read-only.
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
| Local | E2 |
| AWS read | E2 + E3 |
| Deployed | E2 + E3 + E4 |
| Recovery | E2 + E3 + E4 + E5 |

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
| AWS-20 | Bounded deployment | Authorize the exact mutation when the selected lane requires it |
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
