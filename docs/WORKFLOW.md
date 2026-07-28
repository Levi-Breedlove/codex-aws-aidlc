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

## Framework maintenance

Fastlane framework work uses `maintain-fastlane`, never the adopter lifecycle.
It has four modes: `AUDIT` and `PLAN` are read-only; `IMPLEMENT` permits only
local edits inside a recorded baseline, outcome, non-goals, file allowlist,
acceptance criteria, and change budget; and `PUBLISH` requires separate exact
authority for each Git or release action. Missing implementation scope stops
before editing. Unrelated findings remain report-only, and publication never
follows merely from permission to edit.
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
