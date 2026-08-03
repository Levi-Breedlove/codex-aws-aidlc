# AWS Codex Fastlane workflow

Fastlane turns an application idea or bounded change into owner-approved
requirements, one AWS-informed technical design, and a tested local build.
You describe the outcome; Codex recommends and builds; AWS Core supplies current
AWS guidance; the Fastlane Engine keeps scope, state, and authority consistent.

## First run

Send `init template` from a repository created from this template. Fastlane
checks signed-in Codex, Git, Python 3.11+, sandbox support, `uvx`, and current
official AWS Core without inspecting credentials or accessing an AWS account.
Missing items appear in one checklist.

When prerequisites are ready, Fastlane asks these three settings together and
only once:

1. Project name.
2. Preferred AWS Region.
3. Development cost posture or hard cap.

An initialized project resumes from its current state instead of repeating
setup.

## How the conversation works

After the three setup settings, Fastlane asks exactly one unanswered project
question per owner turn. Each decision explains the practical choices, gives a
recommendation when appropriate, names its main tradeoff, and provides a short
copyable reply. Facts already supplied are not asked again.

After each answer, Fastlane confirms what it recorded and the practical effect.
To correct it, reply:

```text
Change <plain field> to <new value>.
```

`Accept all recommendations.` applies only to the current fully explained
recommendation. A correction never approves a gate. A side question is answered
directly and then Fastlane restores the pending project action.

## Lifecycle

| Stage | What Fastlane does | What you do |
|---|---|---|
| Setup and Define | Learns the outcome, users, scope, data, risks, and success | Answer one current question |
| Gate A | Presents the complete Product Owner Brief | Approve requirements or request a correction |
| Design | Uses current AWS Core guidance and compares complete solutions | Nothing unless a business decision is missing |
| Gate B | Presents the complete Technical Owner Brief Pack | Approve design and local construction or request a correction |
| Tasks and Build | Creates dependency-aware work, builds locally, tests, and records evidence | No task-by-task approval |
| Release review | Reconciles what is verified, failed, planned, or still unobserved | Resolve only a genuine release decision |
| Optional AWS operations | Performs separately bounded preflight, deployment, reconciliation, or teardown | Supply the exact action-specific authorization |

Gate A continues into Design in the same run. Gate B continues into task generation
and local construction. Build never deploys.

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

Gate B explains every material technical decision, including application and
edge delivery, identity and authorization, APIs and compute, databases and
access patterns, storage and uploads, messaging and retries, encryption and
secrets, monitoring and incident response, deletion and restoration,
reliability, performance, cost, deployment, rollback, trust boundaries, state
transitions, tests, and the first construction wave.
Gate B also records application source: greenfield uses `app/**`, never `apps/**`
or `src/**`; infrastructure-only records none; brownfield keeps only Gate
A-preserved roots. It adds no gate or routine question.

Each decision states what it means, what was selected, why it fits, alternatives
and rejection reasons, tradeoffs, risks and mitigations, current evidence, claim
status, and a measurable reason to reconsider it. The brief links to the exact
PRD, verification, and runbook sections. Its exact Gate B receipt appears last.

Gate B authorizes only the recorded local construction boundary. It does not
authorize AWS account access, spending, deployment, or teardown.

## Project records

Start at the [project record guide](project/README.md). Fastlane keeps one
canonical set:

- PRD — product agreement, technical plan, Gate A, and Gate B.
- TASKS — current progress, dependencies, and checkpoints.
- VERIFY — observed evidence and honest claim status.
- RUNBOOK — operating, rollback, recovery, and teardown procedures.
- BUGFIX — one bounded defect record when that adjunct is active.

Each record begins with a compact current-state view showing the phase,
one owner need or `Nothing`, what Codex does next, and what remains unapproved or
unauthorized. Human summaries do not replace the exact records.

## AWS Core and AWS authority

Fastlane requires the current official
`aws-core@agent-toolkit-for-aws` from `aws/agent-toolkit-for-aws`. It stores no
raw AWS skill instructions in the project and does not pin a plugin version.
Current AWS evidence is required when service behavior, Region support,
identity, security, reliability, cost, or operations materially affects the
decision.

An AWS lane is a plan, not authority. For AWS preflight, deployment
verification, or teardown preparation, ask Codex to use
`$operate-fastlane-aws`. Read, deployment, and teardown actions retain separate
exact boundaries. Tool availability and credentials never grant permission.

| Optional stage | Purpose | Owner boundary |
|---|---|---|
| AWS-10 | Read-only account preflight | Authorize the exact read-only account and scope |
| AWS-20 | Bounded deployment | Authorize the exact mutation when the selected lane requires it |
| AWS-30 | Reconcile observed results | No new mutation authority |
| AWS-40 | Review residual resources | Choose a residual disposition when required |
| AWS-50 | Bounded teardown | Provide the separate exact teardown authorization |

## Build, resume, and optional hooks

Codex runs dependency-ready tasks serially inside the approved write and command
boundary. Safe Codex-owned mistakes are corrected and revalidated within the
attempt limit. Fastlane stops only for a real owner decision, approval,
authorization, protected boundary, failed evidence, or exhausted limit.

Fastlane works with hooks disabled. The optional hook pack may deny clearly
out-of-bound tool requests after Gate B, but it creates no project state,
approval, or authority. On resume, the Engine restores one current route and
one next action.

Internal engineering methods are conditional techniques, not lifecycle stages
or approval gates. Their procedures stay outside the ordinary owner journey.

## Agent reference

Global invariants live in `AGENTS.md`; phase procedures in Fastlane references;
exact receipts in the prompt registry; deterministic behavior in the Engine and
tests; AWS operations in `operate-fastlane-aws`; and project truth in
`docs/project/`.
