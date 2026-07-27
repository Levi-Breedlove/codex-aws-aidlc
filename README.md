# AWS Codex Fastlane

AWS Codex Fastlane is a reusable project template that turns an AWS idea into
approved requirements, an AWS-informed technical PRD, an organized task plan,
and a safely bounded build.

Requires the Codex CLI, Git, and Python 3.11 or newer. The signed-in
interactive Codex CLI is Fastlane's supported onboarding surface. AWS credentials are
needed only for an explicitly authorized deployment or other approved AWS
operation.

## Start

1. Select [Use this template](https://github.com/Levi-Breedlove/aws-bootstrap/generate)
   and clone the new repository.
2. Open it in a signed-in interactive Codex CLI and send:

   ```text
   init template
   ```

3. Fastlane checks Codex login, Git, Python, platform sandbox tools, `uvx`, and
   official AWS Core. If anything is missing, complete one consolidated
   checklist and send `init template` again.
4. When prerequisites pass, answer three short setup questions:
   - project name;
   - preferred AWS Region; and
   - development budget or "minimize cost; no hard cap."

Codex then configures the template and begins guided intake.
Setup does not inspect AWS credentials or access an AWS account. Detailed
platform commands are in [SETUP.md](docs/SETUP.md).

## What to expect

Gate A — approve requirements → Gate B — approve the PRD and construction boundary → Codex builds autonomously inside that boundary.

Codex asks short, plain-language questions, prefers secure pay-per-use
serverless options when they fit, seeks the lowest practical total cost without
weakening required safeguards, and records evidence.
You can always answer, "I'm not sure—recommend one."

When an approved requirement expresses a testable invariant, Codex records a
`PROP-*` specification, generates framework-appropriate property tests, runs
them during construction, and records reproducible seeds and counterexamples.

AWS changes require a separate exact authorization naming the account, Region,
environment, resources, operations, cost ceiling, rollback plan, and expiry.
Teardown uses a distinct exact authorization.

## AWS Core

Fastlane requires the official AWS Core plugin from the
[AWS Agent Toolkit](https://github.com/aws/agent-toolkit-for-aws) once. Fresh
initialization verifies `aws-core@agent-toolkit-for-aws` from
`aws/agent-toolkit-for-aws`; it does not pin a plugin version or commit.
During AWS work, Codex searches for and retrieves only the runtime skills
relevant to the current decision. Fastlane does not copy AWS skills into the
repository or require separate skill installation. Ordinary requirements and
design need no AWS credentials or AWS account. Initialized projects skip setup,
while material AWS phases require fresh attributable evidence.
Codex's `/plugins` and `/hooks` screens manage installation and trust.
AWS Core advises; it cannot approve a gate or authorize an AWS change.

## Project files

```text
.
├── AGENTS.md                  Always-on Codex rules
├── docs/project/PRD.md        Requirements, design, Gate A, and Gate B
├── docs/project/TASKS.md      Dependency graph and execution state
├── docs/project/VERIFY.md     Observed evidence
├── docs/project/RUNBOOK.md    Deploy, rollback, recovery, and teardown
├── bootstrap.yaml             Derived lifecycle state
├── .agents/skills/            Fastlane workflows
├── .codex/agents/             Optional read-only challengers
├── prompts/CODEX-PROMPTS.md   Exact lifecycle contracts
└── scripts/                   Doctor, task runtime, and packaging tools
```

## Safety

Setup, login, plugin, hook-trust, credential, and machine state stay outside
the repository. Tool availability never authorizes AWS access.

## Agent reference

Detailed references: [setup](docs/SETUP.md) ·
[workflow](docs/WORKFLOW.md) · [security](SECURITY.md) ·
[agent rules](AGENTS.md).
