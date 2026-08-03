# Troubleshooting Fastlane

Fastlane reports one current action whenever possible. Start with that action;
do not regenerate an initialized project to clear an error.

## Read-only checks

Run these from the repository root when Codex asks for diagnostic output:

```text
python scripts/setup_assistant.py prerequisites --root . --json
python scripts/bootstrap_dependencies.py --root . --json
python scripts/bootstrap_doctor.py --root . --json
```

The Fastlane Engine is the bundled read-only validator and lifecycle router.
Its compatibility filename is `scripts/bootstrap_doctor.py`; it is not another
service or installation.

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
controls continue to govern Fastlane. See [Optional Fastlane hooks](HOOKS.md).

## Another blocker appears

Follow the single diagnostic named by the Engine. Preserve dirty files,
approved gates, and canonical project records. If the same safe Codex-owned
correction fails repeatedly, Fastlane should stop for review rather than loop.

Return to the [documentation index](README.md).
