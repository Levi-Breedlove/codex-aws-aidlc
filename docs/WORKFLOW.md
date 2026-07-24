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

Gate B also records a risk-derived Harness Profile. It selects the smallest
exact checks justified by the approved technology, risk, data, identity,
exposure, recovery, and AWS lane; it never imposes a universal scanner.

## Framework maintenance

Fastlane framework work uses `maintain-fastlane`, never the adopter lifecycle.
It has four modes: `AUDIT` and `PLAN` are read-only; `IMPLEMENT` permits only
local edits inside a recorded baseline, outcome, non-goals, file allowlist,
acceptance criteria, and change budget; and `PUBLISH` requires separate exact
authority for each Git or release action. Missing implementation scope stops
before editing. Unrelated findings remain report-only, and publication never
follows merely from permission to edit.


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

## Optional hook guardrails

Fastlane requires no project hooks. Owners who want an additional native Codex
guardrail may manually review and enable the opt-in pack described in
[HOOKS.md](HOOKS.md). It adds read-only doctor context, uses doctor-derived write and external boundaries to deny only clearly unauthorized external or out-of-scope file actions, preserves normal approval
prompts, runs bounded validation, and follows the doctor's automatic-
continuation result.

Hooks never approve a gate or external action. The Fastlane receipts,
construction envelope, AWS authorization, sandbox, and owner approvals remain
authoritative.

## Optional AWS field canaries

The [disposable AWS canary contract](AWS-CANARY.md) defines three representative
field reviews and a standard-library scorer. It is optional, never runs in
ordinary CI, and does not add a lifecycle phase or gate. A real run follows the
same Gate A, Gate B, AWS-10, AWS-20, AWS-30, AWS-40, and AWS-50 controls as any
other AWS delivery. Framework maintenance and the scorer do not access AWS.

## Resume behavior

The doctor selects the next prompt. Fresh templates require current official AWS Core before initialization. Initialized projects skip that prerequisite during normal resume; missing or stale AWS Core evidence later pauses only the affected material AWS step. Correct only the reported blocker, then resume the derived prompt.

Maintainers can run the optional, credential-free-to-validate
[model role-play review](EVALUATION.md) before a release. Live model access is
never part of ordinary CI.
