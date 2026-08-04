# AWS Codex Fastlane setup

This guide is for project owners starting from the template. Fastlane checks
planning dependencies before it writes project configuration. Installation,
plugin enablement, and trust decisions always remain owner-run.

## Normal first run

1. Install and sign in to the
   [official Codex CLI](https://learn.chatgpt.com/docs/codex/cli#getting-started).
2. Create a repository with **Use this template**, clone it, and open the
   repository in interactive Codex.
3. Send `init template`.
4. Fastlane checks Git, Python 3.11+, platform sandbox support, `uvx`, and the
   official AWS Core plugin. If anything is missing, it returns one checklist
   with owner-run setup and verification steps.
5. Complete that checklist, restart Codex when requested, and send
   `init template` again.
6. Answer the three one-time project settings together:
   - project name;
   - preferred AWS Region; and
   - development budget or cost posture.
7. Fastlane configures the template dry-run-first and begins product discovery.

If you do not have a hard budget, answer:

```text
minimize cost; no hard cap
```

After initialization, Fastlane resumes from its recorded project state and
does not repeat prerequisites or setup questions.

## AWS Core walkthrough

Fastlane requires the current official `aws-core` plugin from
`aws/agent-toolkit-for-aws`. It does not pin or copy the plugin.

If AWS Core is missing:

1. In Codex, open `/plugins`.
2. If **Agent Toolkit for AWS** is absent, exit Codex and run:

   ```text
   codex plugin marketplace add aws/agent-toolkit-for-aws
   ```

3. Reopen Codex, open `/plugins`, select **AWS Core** under **Agent Toolkit for
   AWS**, and enable it.
4. Restart Codex, reopen the repository, and send `init template`.
5. Codex performs a credential-free handshake: `search_documentation`
   discovers current runtime skills and `retrieve_skill` loads the exact
   relevant identifier; it does not require separately installed AWS skills.

This handshake does not inspect AWS credentials or access an AWS account.
Other Agent Toolkit plugins are optional and grant no authority.

## Platform dependencies

### Git and Python

Install Git from [git-scm.com](https://git-scm.com/downloads) and Python from
[python.org](https://www.python.org/downloads/) when needed. Verify Git with
`git --version`. Verify Python 3.11+ with `py -3 --version` on Windows or
`python3 --version` on macOS/Linux.

### Linux or WSL2 sandbox

```bash
sudo apt update
sudo apt install bubblewrap
command -v bwrap
bwrap --version
```

WSL1 is unsupported; convert the distribution to WSL2 first.

### Astral uv

Fastlane needs the `uvx` command. Follow the
[official Astral installation guide](https://docs.astral.sh/uv/getting-started/installation/)
and verify with `uvx --version`. Fastlane does not install a package manager
for you.

Ruff is only a Fastlane maintainer and CI check. Project owners do not install
Ruff system-wide to use the template.

## Privacy, hooks, and authority

Prerequisite checks do not persist login, plugin, trust, machine, username,
credential, or AWS-account observations. AWS Core advises; it cannot approve
Gate A, Gate B, deployment, or teardown.
Deployment and teardown retain separate exact Fastlane authority.

Repository hooks are optional and disabled by default. If you choose to enable
them after Gate B, follow [Optional Fastlane hooks](advanced/HOOKS.md). Hook trust stays
in your local Codex profile.

For help, see [Troubleshooting Fastlane](TROUBLESHOOTING.md).
