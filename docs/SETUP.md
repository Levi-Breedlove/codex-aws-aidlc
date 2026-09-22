# AWS Codex Fastlane setup

This guide is for project owners starting from the template. Fastlane checks
planning dependencies before it writes project configuration. Installation,
plugin enablement, and trust decisions always remain owner-run.

Fastlane 1.4 is a local alpha for owner testing. Start with a small, reversible
development project and synthetic data. A local completion has its own evidence;
real AWS operation and recovery qualification remain separate work.

## First-time setup, in order

### 1. Install Codex

Follow the
[official Codex CLI guide](https://learn.chatgpt.com/docs/codex/cli#getting-started),
then verify the installation:

```text
codex --version
```

### 2. Install platform prerequisites

Install Git and Python 3.11 or newer. Linux and WSL2 also require Bubblewrap:

```bash
sudo apt update
sudo apt install bubblewrap
command -v bwrap
bwrap --version
```

WSL1 is unsupported. Verify Git with `git --version`; verify Python with
`py -3 --version` on Windows or `python3 --version` on macOS/Linux.

### 3. Install uv through pipx

Fastlane needs `uvx`. When `pipx` is already installed, run:

```text
pipx install uv
uvx --version
```

Fastlane does not bootstrap a package manager. If `pipx` is unavailable, use
the
[official Astral installation guide](https://docs.astral.sh/uv/getting-started/installation/).

### 4. Add the official AWS Core marketplace

In a terminal, make the current AWS-maintained plugin available:

```text
codex plugin marketplace add aws/agent-toolkit-for-aws
```

Fastlane requires `aws-core` from `aws/agent-toolkit-for-aws`; it does not pin
or copy the plugin and does not require separately installed AWS skills.

### 5. Sign in to Codex

Run the official browser-based sign-in, then verify that Codex reports an
active authentication method:

```text
codex login
codex login status
```

These commands are owner-run. Fastlane does not read or persist the resulting
credentials or account details.

### 6. Install, enable, and verify AWS Core

1. Launch Codex and open `/plugins`.
2. Select **AWS Core** under **Agent Toolkit for AWS**, install it if needed,
   and make sure it is enabled.
3. Restart Codex, reopen `/plugins`, and confirm AWS Core remains enabled.

Other Agent Toolkit plugins are optional and grant no Fastlane authority.

### 7. Review any AWS Core hooks

Open `/hooks`. If Codex lists handlers supplied by the installed AWS Core
plugin, review their exact source and trust them only when you accept them. Do
not add a separate hook file merely because no AWS Core hook is shown. The
official plugin documentation describes skills and AWS MCP configuration; it
does not prescribe a separate manual hook installation.

This step concerns only handlers bundled by AWS Core. Fastlane's own optional
repository hooks remain disabled until a current Gate B approves construction.

### 8. Create the project and initialize Fastlane

1. Create a repository with **Use this template**, clone it, and open it in
   interactive Codex.
2. Send `init template`.
3. Fastlane verifies Git, Python, sandbox support, `uvx`, AWS Core identity,
   and one credential-free handshake that searches current runtime skills and
   retrieves the exact selected identifier.
4. If anything is missing, complete the one consolidated checklist, restart
   Codex when requested, and send `init template` again.
5. Answer the three one-time project settings together: project name, preferred
   AWS Region, and development budget or cost posture.

Name an exact AWS Region such as `us-west-2`, or answer `recommend one` if you
want Fastlane to explain one project-fit recommendation. A recommendation is
not selected automatically: Fastlane waits for you to confirm the exact Region
in a new reply before initialization. A missing or blank Region does not use a
default.

Fastlane then configures the template dry-run-first and presents one **Project
Ready** handoff. It confirms the settings and that AWS access is not authorized,
explains how the consultation works, and asks the first project question.

If you do not have a hard budget, answer:

```text
minimize cost; no hard cap
```

After initialization, Fastlane resumes from its recorded project state and
does not repeat prerequisites, setup questions, or the Project Ready handoff.

Ruff is only a Fastlane maintainer qualification check. Project owners do not
install Ruff system-wide to use the template.

## Privacy, hooks, and authority

Prerequisite checks do not persist login, plugin, trust, machine, username,
credential, or AWS-account observations. AWS Core advises; it cannot approve
Gate A, Gate B, deployment, or teardown.
Deployment and teardown retain separate exact Fastlane authority.

Repository hooks are optional and disabled by default. If you choose to enable
them after Gate B, follow [Optional Fastlane hooks](../.codex/hooks/README.md). Hook trust stays
in your local Codex profile.

After Project Ready, describe your first useful outcome. Fastlane records
concrete input limits, accepted and rejected examples, and the recovery promise
that fits your data before asking you to approve requirements. You can ask
"What will you check, and where will the results be recorded?" at any point.

For help, see [Troubleshooting Fastlane](TROUBLESHOOTING.md).
