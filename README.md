# AWS Codex Fastlane 1.0
Current customer build: **1.0.5**.

Fastlane 1.0 gives Codex a disciplined way to design and build your AWS application. You explain the outcome in plain language. Codex turns it into clear requirements, consults current AWS guidance, recommends a complete design, and builds it after you approve the plan.

Think of Fastlane as the cockpit:

- **You set the destination:** the outcome, constraints, budget, and approvals.
- **Codex pilots:** it plans, recommends, writes, tests, and keeps work moving.
- **AWS Core advises:** it supplies current AWS knowledge and procedures.
- **Fastlane governs:** it records decisions, enforces boundaries, and proves results.

Fastlane prefers secure pay-per-use
serverless options when they fit and seeks the lowest practical total cost without weakening required safeguards.
It never jumps directly to production: two checkpoints keep you in control, and it asks before anything changes in AWS.

## What to expect

1. Describe what you want to accomplish in your own words.
2. Codex asks short, plain-language questions and recommends sensible defaults.
3. At Gate A, you confirm that Fastlane understands the right problem.
4. Codex consults AWS Core, compares credible designs, and recommends one.
5. At Gate B, you approve the complete plan and its construction limits.
6. Codex creates an organized task plan, builds, tests, and records evidence.
7. If you deploy, Fastlane journals the approved attempt, verifies the result read-only, and records that review so resume does not repeat it.

Gate A — approve requirements → Gate B — approve the PRD and construction boundary → Codex builds autonomously inside that boundary.

You do not need an architecture. You can always answer, "I'm not sure—recommend one."

## Start

1. Select [Use this template](https://github.com/Levi-Breedlove/aws-bootstrap/generate)
   and clone the new repository.
2. Open it in a signed-in interactive Codex CLI and send:

   ```text
   init template
   ```

3. Prerequisite baseline: Requires the Codex CLI, Git, and Python 3.11 or newer.
   Fastlane also checks platform sandbox support, `uvx`, and official AWS Core.
   If something is missing, complete the one consolidated checklist and retry.
4. Answer three short setup questions: project name, preferred AWS Region, and
   development budget—or ask Fastlane to minimize cost with no hard cap.

Setup does not inspect AWS credentials or access an AWS account. Platform
instructions are in [SETUP.md](docs/SETUP.md).

## What Fastlane creates

- `docs/project/PRD.md`: what will be built, the recommended design, and both
  approvals.
- `docs/project/TASKS.md`: the dependency-aware work plan and current progress.
- `docs/project/VERIFY.md`: observed evidence, including reproducible seeds and counterexamples.
- `docs/project/RUNBOOK.md`: deployment, rollback, recovery, and teardown steps.

## AWS Core

Fastlane requires the official AWS Core plugin `aws-core@agent-toolkit-for-aws` from the [AWS Agent Toolkit](https://github.com/aws/agent-toolkit-for-aws).
It does not pin a plugin version or commit. During AWS work, Codex discovers and loads only the runtime skills relevant to the current decision.
Fastlane does not copy AWS skills into the
repository or require separate skill installation.
Ordinary requirements and
design need no AWS credentials or AWS account.

Codex chooses the architecture. AWS Core supplies current expertise; it cannot approve or authorize.

## Project files

- `AGENTS.md` contains the always-on operating rules.
- `.agents/skills/` contains workflows; `.codex/agents/` contains optional read-only challengers.
- `prompts/CODEX-PROMPTS.md` contains exact lifecycle and receipt contracts.
- `bootstrap.yaml` mirrors lifecycle state; the bundled **Fastlane Engine**
  validates and routes it through the compatibility file `scripts/bootstrap_doctor.py`.

## Safety

Tool availability never grants authority. `fast-dev` may use only a current Gate B non-production mutation envelope after observed preflight;
`explicit-gate` requires a separate exact authorization receipt. Authenticated AWS reads need current read authority, and teardown stays separately approved.
Setup, login, plugin, trust, credential, and machine state stay outside the repo.

## Agent reference

Detailed references: [setup](docs/SETUP.md) · [workflow](docs/WORKFLOW.md) · [security](SECURITY.md) · [feedback](https://github.com/Levi-Breedlove/aws-bootstrap/issues/new?template=fastlane-feedback.yml) · [agent rules](AGENTS.md).
