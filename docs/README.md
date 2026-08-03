# Fastlane documentation

Use this page to find the right Fastlane guide without reading internal
implementation instructions.

## Start here

- [Set up Fastlane](SETUP.md) — install the owner-run prerequisites and start a
  fresh template.
- [Understand the workflow](WORKFLOW.md) — see the complete owner journey from
  idea through local construction and optional AWS operations.
- [Troubleshoot](TROUBLESHOOTING.md) — resolve setup, resume, AWS Core, and
  Engine blockers without regenerating an active project.
- [Security policy](../SECURITY.md) — understand trust, data, credentials, and
  authorization boundaries.

## Project records

Initialized projects use one canonical record set under
[`docs/project/`](project/README.md):

- [PRD](project/PRD.md) — product agreement, technical plan, Gate A, and Gate B.
- [Tasks](project/TASKS.md) — work status, dependencies, and checkpoints.
- [Verification](project/VERIFY.md) — observed tests and operational evidence.
- [Runbook](project/RUNBOOK.md) — deployment, rollback, recovery, and teardown.
- [Bugfix record](project/BUGFIX.md) — one bounded defect investigation when
  that adjunct is active.

These files begin with a plain-language current-state view. Exact records remain
in the same document; Fastlane never creates a separate human PRD.

## Optional operator features

- [Hooks](HOOKS.md) — optional post-Gate-B defense in depth. Fastlane remains
  correct when hooks are disabled.
- [Dependency policy](DEPENDENCY-POLICY.md) — AWS Core, Ruff, and GitHub Actions
  maintenance boundaries.

## Maintainers

- [Evaluation overview](EVALUATION.md) — what owner/AI and field qualification
  can and cannot prove.
- [Workflow](WORKFLOW.md) — the owner-visible lifecycle that maintenance must
  preserve.
- Framework procedures live in `maintain-fastlane`; deterministic behavior
  lives in the Engine and tests.

Fastlane has exactly two routine owner gates. Tool availability, hooks, AWS
Core, and GitHub access never create approval or authorization.
