# Troubleshooting Fastlane

This guide helps you continue Fastlane's requirements, design, implementation,
verification, and AWS delivery workflow when a step needs attention. Fastlane
reports one current action whenever possible. Start with that action; do not
regenerate an initialized project to clear an error. For the full product and
lifecycle, see the [overview](../README.md) and [workflow guide](WORKFLOW.md).

| Symptom | Start here |
|---|---|
| You need safe diagnostic output | [Read-only checks](#read-only-checks) |
| A Codespaces command is unavailable or the wrong version opens | [Codespaces setup and resume](#codespaces-setup-and-resume) |
| Workspace checks passed but AWS has not changed | [Construction and AWS delivery](#construction-and-aws-delivery) |
| Setup repeats | [`init template` repeats setup](#init-template-repeats-setup) |
| AWS Core is unavailable | [AWS Core is missing](#aws-core-is-missing) |
| Current AWS guidance cannot be retrieved | [AWS Core research fails later](#aws-core-research-fails-later) |
| A prior approval is no longer current | [A gate becomes stale](#a-gate-becomes-stale) |
| An optional hook blocks valid work | [Optional hooks deny a valid action](#optional-hooks-deny-a-valid-action) |
| A check or evidence binding is rejected | [Check and evidence correction](#a-check-or-evidence-record-is-rejected) |
| An older project needs additional records | [Existing-project compatibility](#an-older-project-needs-new-records) |
| The Engine reports another blocker | [Another blocker appears](#another-blocker-appears) |

## Read-only checks

Run these from the repository root when Codex asks for diagnostic output:

The examples use `python3` for macOS, Linux, and Codespaces. On Windows, replace
`python3` with `py -3`. Use the same Python 3.11-or-newer interpreter throughout.

```text
python3 scripts/setup_assistant.py prerequisites --root . --json
python3 scripts/bootstrap_dependencies.py --root . --json
python3 scripts/bootstrap_doctor.py --root . --json
```

The Fastlane Engine is the bundled read-only validator and lifecycle router.
Its compatibility filename is `scripts/bootstrap_doctor.py`; it is not another
service or installation.

## Codespaces setup and resume

Check the branch and commit in the Codespaces terminal against the candidate
you intended to open. A new Codespace may use a different branch; reopening an
existing Codespace retains that workspace's state. Preserve local changes
before synchronizing it. Use the [Codespaces walkthrough](SETUP.md#github-codespaces).

If `python`, Codex, Git, `uvx`, or Bubblewrap is missing, check the Linux setup
steps in that environment. `python3` can exist when `python` does not. After an
owner-run installation or plugin change, reopen the terminal or restart Codex
as requested and retry the same pending step. Never clear the canonical project
records to repair a missing tool. For a sign-in callback failure, use the
[official remote sign-in guidance](https://learn.chatgpt.com/docs/auth).

## Construction and AWS delivery

Fastlane's build stage edits and checks the approved project inside its development
workspace, whether on your computer or in a Codespace. A local result describes
that evidence; it does not restrict where the finished application can run.

Ask Codex what target is complete and which delivery step comes next. AWS account
preflight, deployment, recovery, and teardown require their applicable exact
authorization and observed results. Gate B and a passing build do not authorize
those operations. Continue from the existing project records and the
[AWS delivery stages](WORKFLOW.md#aws-core-and-aws-authority).

## `init template` repeats setup

For a fresh template, complete the prerequisite checker’s single checklist and
send `init template` again. An initialized project should resume from the
Engine-selected stage without repeating prerequisites or project settings.

If it does not, preserve the repository and report the Engine diagnostic. Do
not delete `bootstrap.yaml` or replace project records.

## AWS Core is missing

1. Open `/plugins` in Codex.
2. If **Agent Toolkit for AWS** is absent, run:

   ```text
   codex plugin marketplace add aws/agent-toolkit-for-aws
   ```

3. Enable **AWS Core**, restart Codex, and retry the same step.

See the complete [setup walkthrough](SETUP.md). Fastlane never asks to inspect
AWS credentials, private trust storage, or an AWS account during setup.

## AWS Core research fails later

Pause only the affected AWS-specific design or operating step. Confirm the
official plugin is enabled, restart Codex once, and retry. Do not replace
missing current evidence with cached prose, memory, or a reviewer’s claim.

## A gate becomes stale

A changed requirement stales Gate A and Gate B. A changed technical design or
construction boundary stales Gate B. Follow the Engine’s correction action,
review the refreshed brief, and use only the new exact receipt.

## Optional hooks deny a valid action

Hooks are optional. Review `/hooks`, remove the local `.codex/hooks.json`, and
restart Codex to disable them. The Engine and normal Codex approval/sandbox
controls continue to govern Fastlane. See [Optional Fastlane hooks](../.codex/hooks/README.md).

## A check or evidence record is rejected

Ask Codex to explain the current validation plan. It will show the exact check,
time limit, result location, and any mismatch with the approved command boundary.
Commands must match the approved text, including spaces inside quotes. Ask Codex
to restore the approved command and rerun it; if the command needs to change,
review that change through the existing design step. Keep prior evidence intact.
It can also produce a read-only diagnostic:

```text
python3 scripts/bootstrap_doctor.py --root . --explain-validation --json
```

An old pass cannot establish a changed acceptance outcome or a new task attempt.
Keep the old result, correct the current binding or implementation, and rerun the
affected check inside its approved boundary. A later failure remains blocking
until a later current result passes. A missing tool is a prerequisite gap, not a
passing result or permission to install software.

If the result location is missing or belongs to a different kind of check,
Codex must reconcile it with the appropriate verification section before
presenting the technical plan for approval. Restoring a section restores a
place to record evidence; it does not create a passing result.

If recovery wording conflicts, resolve the promise first: recreating a synthetic
fixture does not prove that a backup can restore durable data. If an input limit
is unresolved, state the accepted and rejected cases before approving it.

## An older project needs new records

Resume the existing project. Exact unchanged approvals remain readable; do not
delete records or copy new headings into an old approval to force a pass. Codex
will identify the missing decisions and refresh only the affected requirements,
design, gates, tasks, and evidence. A material requirement change needs both
approvals again; a design change needs the technical approval again.

## Another blocker appears

Follow the single diagnostic named by the Engine. Preserve dirty files,
approved gates, and canonical project records. If the same safe Codex-owned
correction fails repeatedly, Fastlane should stop for review rather than loop.

Return to the [documentation index](README.md).
