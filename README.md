# AWS Codex Fastlane 1.1

Current customer build: **1.1.3**.

Fastlane Engine gives Codex a disciplined way to turn an AWS idea into clear
requirements, one recommended design, and a tested local build. You explain
the outcome in plain language; Codex plans while you control consequential choices.

- **You set the destination:** outcome, constraints, budget, and approvals.
- **Codex pilots:** it asks, recommends, writes, tests, and keeps work moving.
- **AWS Core advises:** it supplies current AWS knowledge and procedures.
- **Fastlane governs:** it records decisions, enforces boundaries, and proves results.

Fastlane favors secure pay-per-use serverless options when they fit and seeks the
lowest practical total cost without weakening required safeguards. It never jumps directly to production.

## What to expect

1. Describe what you want to accomplish in your own words.
2. Codex asks one short question at a time and recommends sensible defaults.
3. At Gate A, you confirm the complete product agreement.
4. Codex consults AWS Core, compares credible designs, and recommends one.
5. At Gate B, you approve the full technical design and construction limits.
6. Codex creates tasks, builds locally, tests, and records observed evidence.
7. Any AWS account operation follows a separate, exact authorization.

Gate A — approve requirements → Gate B — approve the PRD and construction boundary → Codex builds autonomously inside that boundary.

You do not need an architecture. You can always say, “I’m not sure; recommend one.”

## Start

1. Select [Use this template](https://github.com/Levi-Breedlove/aws-bootstrap/generate) and clone the new repository.
2. Open it in a signed-in interactive Codex CLI and send:

   ```text
   init template
   ```

3. Fastlane checks Codex, Git, Python 3.11+, sandbox support, `uvx`, and the
   official AWS Core plugin. If needed, it provides one consolidated checklist.
4. Answer the three one-time settings: project name, preferred AWS Region, and
   development budget or “minimize cost; no hard cap.”

Setup does not inspect AWS credentials or access an AWS account. See the [setup walkthrough](docs/SETUP.md)
and [troubleshooting guide](docs/TROUBLESHOOTING.md).

## Repository map

- `app/`: the one reserved greenfield application root.
- `tests/`: application and infrastructure verification.
- `infrastructure/`: infrastructure as code and deployment definitions.
- `docs/project/`: canonical requirements, design, tasks, evidence, operations, and defects.
- `.agents/` and `prompts/`: scoped instructions used by Codex.
- `scripts/`: deterministic Fastlane Engine and supporting validators.

Start with the [documentation index](docs/README.md) or [project record guide](docs/project/README.md).

## AWS Core and AWS changes

Fastlane requires the official AWS Core plugin from the
[AWS Agent Toolkit](https://github.com/aws/agent-toolkit-for-aws). It uses `aws-core@agent-toolkit-for-aws`, discovers current runtime skills, and does not copy AWS skills into the
repository. Fastlane does not pin a plugin version or commit.

Codex chooses the architecture. AWS Core supplies current expertise; it cannot approve or authorize.
Ordinary requirements and
design need no AWS credentials or AWS account.

After Gate B, Codex builds locally. For AWS preflight, deployment verification,
or teardown preparation, ask Codex to use `$operate-fastlane-aws`. Fast Dev stays
inside a current non-production Gate B envelope; explicit-gate deployment and
teardown require their own exact receipts. Tool availability never grants authority.

## Learn more

- [Understand the workflow](docs/WORKFLOW.md)
- [Optional hooks](docs/HOOKS.md)
- [Dependency policy](docs/DEPENDENCY-POLICY.md)
- [Security](SECURITY.md)
- [Maintainer evaluation](docs/EVALUATION.md)
