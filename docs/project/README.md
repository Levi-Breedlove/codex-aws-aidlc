# Project record guide

This folder holds the durable project records Fastlane uses to define, design, build, verify, and operate your software or infrastructure project.
<!-- FASTLANE:DOCUMENT_SUMMARY:BEGIN -->
## Current state

| Field | Current value |
|---|---|
| Phase | Not yet initialized |
| Overall status | Not yet initialized |
| Last completed milestone | None |
| Gate A | Not yet initialized |
| Gate B | Not yet initialized |
| AWS deployment | Not deployed |
| Construction tasks | No tasks generated |
| Verification | Not yet initialized |
| Operations | Not deployed |
| Bounded defect | No active bounded defect |
| AWS account access | Not authorized |
| Updated | Not yet initialized |
| Need from you | Run `init template`. |
| Next | Codex will verify prerequisites and initialize the project. |

## Go directly to

- [Product and technical plan](PRD.md#product-agreement)
- [Construction progress](TASKS.md#current-progress)
- [Verification and evidence](VERIFY.md#current-result)
- [Operations runbook](RUNBOOK.md#safety-boundary)
- [Bounded defect record](BUGFIX.md#current-state)
<!-- FASTLANE:DOCUMENT_SUMMARY:END -->

## Project records

| Record | What the owner finds there |
|---|---|
| [Product and technical plan](PRD.md) | Product Agreement, architecture recommendation, Gate A, and Gate B |
| [Construction progress](TASKS.md) | Roadmap, active work, blockers, and validation |
| [Verification and evidence](VERIFY.md) | What is confirmed, observed, planned, failed, or still unobserved |
| [Operations runbook](RUNBOOK.md) | Validate, deploy, verify, roll back, recover, and tear down |
| [Bounded defect](BUGFIX.md) | The current focused repair, when BUG-10 is active |

Start with the current Fastlane conversation action. Owner Decision Briefs link
back to readable sections in these same canonical records. Together, the records
connect requirements to architecture, implementation tasks, verification results,
and operating procedures, so Codex can resume the agreed work in a later session.

For the complete product lifecycle, see the [workflow guide](../WORKFLOW.md).
Workspace checks, AWS observations, deployment, and recovery retain their own
evidence; a planned operating procedure does not establish that it was executed.

## Record integrity

Project facts stay in these canonical files. Fastlane validates their exact
records while keeping internal procedures and syntax out of the owner path.
