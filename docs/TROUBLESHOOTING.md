# Troubleshooting Fastlane

Run these read-only checks from the repository root:

```text
python scripts/setup_assistant.py prerequisites --root . --json
python scripts/bootstrap_dependencies.py --root . --json
python scripts/bootstrap_doctor.py --root . --json
```
The Fastlane Engine is the bundled read-only validator and lifecycle router.
Its compatibility filename remains `scripts/bootstrap_doctor.py`; it is not
another service or installation.


## `init template` keeps repeating setup

For a fresh template, complete the prerequisite checker's single checklist,
then send `init template` again. After configuration, use the Fastlane Engine's
interaction state; initialized projects do not rerun prerequisites or setup
questions.

## AWS Core is missing during prerequisites

1. If **Agent Toolkit for AWS** is absent from `/plugins`, run:

   ```text
   codex plugin marketplace add aws/agent-toolkit-for-aws
   ```

2. Enable **AWS Core** under **Agent Toolkit for AWS**.
3. Restart Codex and send `init template`.
4. Codex will verify both documentation-only capabilities without AWS access.

Fastlane does not pin the plugin version or commit, inspect private trust
storage, or persist plugin state.

## Codex CLI or local runtime is missing

Use the [official Codex CLI getting-started guide](https://learn.chatgpt.com/docs/codex/cli#getting-started).
Linux or WSL2 sandbox and `uv` commands are in [SETUP.md](SETUP.md).
Installation remains owner-run.

## AWS Core research fails

On a fresh template, remain at prerequisites. On an initialized project, stop
only the affected design or AWS operating step. Confirm the capability is from
`aws-core@agent-toolkit-for-aws`, restart Codex once, and retry the same step.
Do not regenerate an initialized project, request hook screenshots, compare
hook hashes, or run synthetic probes.

## Fastlane Engine reports another blocker

Follow the single diagnostic named by the Engine. Preserve the repository,
dirty files, approved gates, and project ledgers; do not regenerate an active
project to clear an error.
