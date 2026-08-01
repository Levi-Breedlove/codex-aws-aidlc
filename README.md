# AWS Codex Fastlane 1.1
Current customer build: **1.1.0**.

Fastlane Engine gives Codex a disciplined way to turn your AWS idea into clear requirements, one recommended design, and a tested local build. You explain the outcome in plain language; Codex handles the technical planning and keeps you in control of consequential choices.

Think of Fastlane as the cockpit:

- **You set the destination:** outcome, constraints, budget, and approvals.
- **Codex pilots:** it asks, recommends, writes, tests, and keeps work moving.
- **AWS Core advises:** it supplies current AWS knowledge and procedures.
- **Fastlane governs:** it records decisions, enforces boundaries, and proves results.

Fastlane favors secure pay-per-use
serverless options when they fit and seeks the lowest practical total cost without weakening required safeguards. It never jumps directly to production.

## What to expect

1. Describe what you want to accomplish in your own words.
2. Codex asks short, plain-language questions and recommends sensible defaults.
3. At Gate A, you confirm that Fastlane understands the right problem.
4. Codex consults AWS Core, compares credible designs, and recommends one.
5. At Gate B, you approve the design and construction limits.
6. Codex creates an organized task plan, builds locally, tests, and records evidence.
7. Any AWS account operation follows a separate, exact authorization.

Gate A — approve requirements → Gate B — approve the PRD and construction boundary → Codex builds autonomously inside that boundary.

You do not need an architecture. You can always say, "I'm not sure; recommend one."

## Start

1. Select [Use this template](https://github.com/Levi-Breedlove/aws-bootstrap/generate) and clone the new repository.
2. Open it in a signed-in interactive Codex CLI and send:

   ```text
   init template
   ```

3. Fastlane checks the Codex CLI, Git, Python 3.11+, platform sandbox support, `uvx`, and official AWS Core. Complete its one consolidated checklist if needed.
4. Answer three setup questions: project name, preferred AWS Region, and development budget-or ask Fastlane to minimize cost with no hard cap.

Setup does not inspect AWS credentials or access an AWS account.

## Project files

Start with the [project record guide](docs/project/README.md).

- `docs/project/PRD.md`: requirements, recommended design, and both approvals.
- `docs/project/TASKS.md`: dependency-aware work and current progress.
- `docs/project/VERIFY.md`: observed test and operational evidence.
- `docs/project/RUNBOOK.md`: deployment, rollback, recovery, and teardown steps.

## AWS Core and AWS changes

Fastlane requires the official AWS Core plugin: `aws-core@agent-toolkit-for-aws` from `aws/agent-toolkit-for-aws` in the [AWS Agent Toolkit](https://github.com/aws/agent-toolkit-for-aws). It uses the current release and does not pin a plugin version or commit. Codex discovers and loads only the AWS skills relevant to the current decision. Fastlane does not copy AWS skills into the
repository. Ordinary requirements and
design need no AWS credentials or AWS account.

Codex chooses the architecture. AWS Core supplies current expertise; it cannot approve or authorize.

After Gate B, Codex builds locally. For AWS preflight, deployment verification, or teardown preparation, ask Codex to use `$operate-fastlane-aws`. Every AWS mutation still requires its exact separate authorization.

## Safety

Tool availability never grants authority. Fast Dev stays inside a current non-production Gate B envelope; explicit-gate deployment and teardown require their own exact receipts. Setup, login, plugin, trust, credential, and machine state stay outside the repository.

## Agent reference

- [Get started](docs/SETUP.md)
- [Understand the workflow](docs/WORKFLOW.md)
- [Troubleshoot](docs/TROUBLESHOOTING.md)
- [Security](SECURITY.md)
- [Optional hooks](docs/HOOKS.md)
- [Maintainer evaluation](docs/EVALUATION.md)
