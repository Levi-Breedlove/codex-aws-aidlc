# AWS Codex Fastlane Setup

Fastlane verifies local planning tools before changing a fresh template. Every
check is read-only and every installation or trust action remains owner-run.
The signed-in interactive Codex CLI is the supported Fastlane 1.0 onboarding
surface.

## Normal first run

1. Install Codex CLI from the
   [official getting-started guide](https://learn.chatgpt.com/docs/codex/cli#getting-started),
   then sign in:

   ```text
   codex --version
   codex login
   codex login status
   ```

2. Create a repository with **Use this template**, open it in interactive
   Codex CLI, and send `init template`.
3. Fastlane checks Git, Python 3.11+, platform sandbox support, `uvx`, and
   official AWS Core.
4. If something is missing, Fastlane returns one consolidated checklist. Each
   item distinguishes an owner-run install or action, an official guide when
   platform choice is required, and the exact verification command. Fastlane
   never bootstraps a package manager.
5. Complete the checklist and send `init template` again.
6. Answer a one-line project name, a canonical AWS Region ID such as `us-west-2`,
   and an optional budget exactly once. Ordinary punctuation and international
   project names are supported; AWS Core verifies current Region availability later.
7. Fastlane configures the template dry-run-first and begins Define.

If you do not have a hard budget, answer:

```text
minimize cost; no hard cap
```

## Official AWS Core and runtime skills

Fastlane requires only the current official `aws-core` plugin from
`aws/agent-toolkit-for-aws`. It does not pin a version or commit, and
installation and native trust remain in the owner's local Codex profile.

When AWS Core is missing:

1. In interactive Codex, open `/plugins`.
2. If **Agent Toolkit for AWS** is absent, exit Codex and run:

   ```text
   codex plugin marketplace add aws/agent-toolkit-for-aws
   ```

3. Reopen `/plugins`, select **AWS Core** under **Agent Toolkit for AWS**,
   and enable it.
4. Restart Codex, reopen the project, and send `init template`.
5. Codex performs one credential-free runtime handshake:
   - `search_documentation` discovers current AWS skill identifiers;
   - Codex selects the smallest relevant returned skill set; and
   - `retrieve_skill` loads the exact selected identifier.

Fastlane does not copy raw skill instructions into the repository. Initialization
does not require separately installed AWS skills, the AWS CLI skill installer,
AWS credentials, or an AWS account. Skills installed by other supported methods
may be convenient, but they do not replace the runtime discovery evidence.

Other Agent Toolkit plugins are optional and grant no authority. Fastlane does
not ask the owner to choose one during setup. See the current
[AWS plugin catalog](https://docs.aws.amazon.com/agent-toolkit/latest/userguide/plugins.html).

If Codex asks you to review plugin hooks, use its native `/hooks` screen.
Fastlane does not compare hook hashes, request screenshots, run synthetic hook
probes, inspect private trust storage, or ask for a separate trust receipt.

## Platform prerequisites

### Git and Python

Use the [official Git installer](https://git-scm.com/downloads) and
[official Python downloads](https://www.python.org/downloads/) when your
platform requires an installer choice. Verify Git with `git --version`.
Verify Python 3.11+ with `py -3 --version` on Windows or
`python3 --version` on macOS/Linux.

### Linux or WSL2 sandbox

```bash
sudo apt update
sudo apt install bubblewrap
command -v bwrap
bwrap --version
```

WSL1 is unsupported; convert the distribution to WSL2 first and verify it with
`wsl -l -v`.

### Astral uv

Fastlane first suggests `pipx install uv` when `pipx` is already available.
Otherwise it uses a current official Astral command for the detected platform.
Always verify with `uvx --version`. See the
[official Astral installation guide](https://docs.astral.sh/uv/getting-started/installation/).

## Resume, privacy, and authority

Initialized projects skip the prerequisite gate during ordinary resume. Missing
or stale AWS Core evidence later pauses only the affected material AWS phase.

During prerequisite checks, Fastlane does not persist login, plugin, trust,
machine, credential, username, or AWS-account observations. Later gated and AWS
operations intentionally record audit metadata—including an approver handle,
stable source reference, account or approved alias, role, Region, resources,
and observed results—in project evidence. Review or protect those records
before publishing the repository.

AWS Core provides knowledge, procedures, and tools; it cannot approve Gate A,
Gate B, deployment, or teardown. Prerequisite success grants no AWS access.
Deployment and teardown retain separate exact Fastlane authority.
