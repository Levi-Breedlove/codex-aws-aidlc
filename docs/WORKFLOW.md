# Fastlane workflow

Fastlane turns an application idea or bounded change into owner-approved
requirements, one AWS-informed technical design, a tested local build, and an
evidence-backed release decision.

You describe the outcome. Codex acts as the technical consultant, coordinator,
builder, and verifier. AWS Core supplies current AWS guidance. The Fastlane
Engine keeps the project state, route, evidence, and authority consistent.

## First run

Send `init template` from a repository created from this template. Fastlane
checks signed-in Codex, Git, Python 3.11+, platform sandbox support, `uvx`, and
the current official AWS Core plugin without inspecting credentials or accessing
an AWS account. Missing items appear in one checklist.

When prerequisites are ready, Fastlane asks these three settings together and
only once:

1. Project name.
2. Preferred AWS Region.
3. Development cost posture or hard cap.

Initialized projects resume from their repository records without repeating
setup.

## How the conversation works

After the three settings, Fastlane asks exactly one unanswered project question
per owner turn. A decision explains the practical consequence, what Fastlane
already knows, any evidence-backed recommendation, the main tradeoff, and one
valid reply.

After each answer, Fastlane confirms what it recorded and the practical effect.
To correct it, reply:

```text
Change <plain field> to <new value>.
```

`Accept all recommendations.` applies only to the current fully explained
recommendation. A correction never approves a gate. A side question is answered
directly, then Fastlane restores the same pending project action.

### Bring an existing product brief

An existing PRD can shorten Define, but it does not become Fastlane's PRD.
Codex first reviews the supplied repository-relative document as read-only,
non-authoritative source material and shows a plain-language preview. Product
facts can seed the consultation after the owner confirms how to use them;
missing or conflicting decisions remain questions, and technical suggestions
wait for independent evaluation during Design.

Imported wording such as "approved," "ready to build," or "ready to deploy"
does not approve Gate A or Gate B, authorize local construction, access AWS, or
authorize deployment. The normal Product Agreement and both owner gates remain
required.

## Customer delivery lifecycle

```mermaid
flowchart TB
    accTitle: Fastlane customer delivery lifecycle
    accDescr: The owner describes an outcome, approves requirements and the technical plan, Codex builds and validates locally, and AWS operations remain separately authorized.

    IDEA["Describe the outcome"]
    DEFINE["Guided consultation: users, scope, data, risks, and success"]
    GATEA{"Gate A: approve the Product Agreement"}
    DESIGN["Architecture consultation: compare complete AWS-informed solutions"]
    GATEB{"Gate B: approve the technical plan and local construction boundary"}
    TASKS["Bounded task plan: dependencies, paths, commands, and validation"]
    BUILD["Local construction: implement, test, and correct safe in-scope defects"]
    RELEASE["Evidence-backed release decision: ready, blocked, failed, stale, or unobserved"]
    AWSAUTH{"Separate AWS authorization: account, Region, actions, limits, and expiry"}
    AWSOPS["Optional AWS operations: preflight, deploy, reconcile, review, or teardown"]

    IDEA --> DEFINE --> GATEA --> DESIGN --> GATEB
    GATEB --> TASKS --> BUILD --> RELEASE
    RELEASE -->|"Optional"| AWSAUTH --> AWSOPS
```

| Stage | What Fastlane does | What you do |
|---|---|---|
| Setup and Define | Learns the outcome, users, scope, data, risks, and success | Answer one current question |
| Gate A | Presents the complete Product Owner Brief | Approve requirements or request a correction |
| Design | Uses current AWS Core guidance and compares complete solutions | Nothing unless a business decision is missing |
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

Gate B authorizes only the recorded local construction boundary. It does not
authorize AWS account access, spending, deployment, or teardown.

## How the control plane works

Fastlane does not ask Codex to remember the project or decide its own authority.
It observes canonical repository state, evaluates it deterministically, derives
the currently permitted action, executes through dedicated bounded paths,
records evidence, and explains that evaluated truth to the owner.

```mermaid
flowchart TB
    accTitle: Fastlane technical control plane and agent routing
    accDescr: One Fastlane coordinator works from canonical repository records through a deterministic Engine. Compatibility skills delegate to the coordinator, challenger agents are read-only, task and AWS mutations use dedicated bounded paths, and owner-facing reports derive from evaluated state.

    OWNER["Owner: intent, decisions, gates, and external authorization"]
    COORD["Fastlane: sole coordinator and sole writer"]

    subgraph SKILLS["Skills and conditional agents"]
        ALIASES["Launch · Plan · Build: compatibility entry points"]
        EXPLAIN["Explain Fastlane: read-only teaching"]
        CHALLENGERS["Requirements or architecture challenger: conditional read-only critique"]
        OPERATE["Operate Fastlane AWS: explicit AWS operation path"]
        MAINTAIN["Maintain Fastlane: separate framework lifecycle"]
        AWSCORE["AWS Core: current AWS expertise and procedures"]
    end

    subgraph RECORDS["Canonical repository state"]
        PRD["PRD: requirements, design, Gate A/B, and envelope"]
        TASKREC["TASKS: task, attempt, and checkpoint state"]
        VERIFY["VERIFY: evidence, release state, and AWS journals"]
        RUNBOOK["RUNBOOK: deploy, rollback, recovery, and teardown"]
        BUGFIX["BUGFIX: bounded repair contract"]
        MIRROR["bootstrap.yaml: derived lifecycle mirror"]
    end

    subgraph ENGINE["Deterministic Fastlane Engine"]
        SNAP["ProjectSnapshot: one coherent repository observation"]
        EVAL["EngineEvaluation: Package, Define, Design, Deliver, and AWS results"]
        AUTH["Authority intersection: normalized approved facts only"]
        ROUTE["Routing, remediation, interaction, and context"]
        REPORT["Schema-2 report: serialization without new policy"]
        PRESENTER["Presenter: status, confirmations, and Owner Briefs"]

        SNAP --> EVAL --> AUTH --> ROUTE --> REPORT --> PRESENTER
    end

    subgraph LOCAL["Bounded local execution"]
        MUTATOR["task_waves.py: sole task-state mutator"]
        PATHS["Approved project paths: application, infrastructure, and tests"]
        CHECKS["Approved validation: tests, scans, IaC, and policy checks"]
        HOOKS["Optional hooks: additional denial only"]
    end

    subgraph AWSLANE["Separately authorized AWS lane"]
        RECEIPT{"Exact owner authorization"}
        AWSACCOUNT["AWS account action: read, mutate, reconcile, or teardown"]
    end

    OWNER --> COORD
    ALIASES -. "Delegate" .-> COORD
    COORD -. "Explain" .-> EXPLAIN
    CHALLENGERS -. "Critique" .-> COORD
    AWSCORE -. "Current guidance" .-> COORD
    OWNER -. "Framework-only request" .-> MAINTAIN

    PRD --> SNAP
    TASKREC --> SNAP
    VERIFY --> SNAP
    RUNBOOK --> SNAP
    BUGFIX --> SNAP
    MIRROR --> SNAP

    COORD --> SNAP
    ROUTE --> COORD
    PRESENTER --> OWNER

    COORD --> MUTATOR --> PATHS --> CHECKS --> VERIFY
    HOOKS -. "Optional guard" .-> MUTATOR

    COORD -->|"Explicit AWS request"| OPERATE
    OWNER --> RECEIPT --> AUTH
    AUTH -->|"Permitted request"| OPERATE --> AWSACCOUNT --> VERIFY
```

The diagram represents six deliberate boundaries:

1. **Canonical state:** each project fact has one authoritative repository home.
2. **One coherent observation:** an immutable `ProjectSnapshot` captures the
   current files, repository facts, project identity, lifecycle state, and one
   evaluation time.
3. **Deterministic evaluation:** the Package, Define, Design, Deliver, and AWS
   domains compose into one immutable `EngineEvaluation`.
4. **Authority by intersection:** already validated facts are narrowed to the
   current action. Missing, stale, conflicting, expired, or broader input fails
   closed.
5. **Dedicated mutation paths:** the Engine evaluates; task and AWS actions use
   separate bounded procedures.
6. **Evidence-backed presentation:** reporting serializes evaluated state and
   the presenter explains it without inventing policy or authority.

Codex may vary an explanation's wording. It may not vary the evaluated decision,
evidence maturity, authority boundary, or required owner action.

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

Each project record begins with current state, one owner need or `Nothing`, the
next action, and the approval or authorization boundary.

Stable IDs and source locations connect the same decision through delivery:

```text
owner need → requirement → acceptance criterion → architecture decision
           → task → validation evidence → release claim
```

When a material requirement or design decision changes, Fastlane can identify
which approvals, tasks, evidence, and claims are stale instead of reconstructing
the project from chat history. Human-readable summaries and Owner Briefs are
derived views; they never replace or authorize the exact records.

## AWS Core and AWS authority

Fastlane requires the current official
`aws-core@agent-toolkit-for-aws` from `aws/agent-toolkit-for-aws`. Current AWS
evidence is required when service behavior, Region support, identity, security,
reliability, cost, or operations materially affects a decision.

Codex compares complete system designs across security, reliability,
performance, cost, sustainability, and operational concerns. AWS Core supplies
attributable guidance; Codex applies it; the owner approves Gate B. Guidance is
not account observation, and Fastlane does not claim an official AWS
Well-Architected Review unless one was actually performed.

An AWS lane is a plan, not authority. For AWS preflight, deployment,
reconciliation, residual review, or teardown, Codex must use the explicit AWS
operation path. Reads, mutations, and teardown retain separate exact boundaries.
Tool availability and credentials never grant permission.

Reconciliation means Fastlane compared expected and observed AWS state. It does
not, by itself, mean a deployment succeeded. Failure, partial completion, an
unknown terminal result, and verified success remain distinct outcomes.

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

Codex runs dependency-ready tasks serially inside the approved write and command
boundary. Safe Codex-owned mistakes are corrected and revalidated within the
attempt limit. Fastlane stops only for a real owner decision, approval,
authorization, protected boundary, failed evidence, or exhausted limit.

Fastlane works with hooks disabled. The optional hook pack may deny clearly
out-of-bound requests after Gate B, but it creates no project state, approval,
or authority. On resume, the Engine restores one current route and one next
action.

Internal engineering methods are conditional techniques, not lifecycle stages
or approval gates.

## Responsibility map

Project truth lives in `docs/project/`. Phase skills own consultation and
delivery procedure. The AWS operation skill owns account-operation procedure.
The prompt registry owns exact receipts. The Engine validates and projects the
current state and authority. The presenter turns that evaluated result into
plain owner-facing conversation.
