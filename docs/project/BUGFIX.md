# {{PROJECT_NAME}} — Bugfix Specification

Canonical path: `docs/project/BUGFIX.md`.

Use this file for the active defect or regression. Archive or reset it after the fix is complete.
<!-- FASTLANE:DOCUMENT_SUMMARY:BEGIN -->
## Current state

| Field | Current value |
|---|---|
| Status | No active bounded defect |
| Defect | None |
| User impact | None |
| Reproduction | Not active |
| Environment | Not active |
| Related requirements | None |
| Root cause | Not active |
| Repair | Not active |
| Regression evidence | Not active |
| Architecture impact | None |
| Updated | Not yet initialized |
| Need from you | Run `init template`. |
| Next | Codex will verify prerequisites and initialize the project. |

## Go directly to

- [Summary](#1-summary)
- [Current behavior](#2-current-behavior)
- [Root-cause analysis](#7-root-cause-analysis)
- [Fix constraints](#8-fix-constraints)
- [Regression evidence](#9-regression-and-property-specification)
<!-- FASTLANE:DOCUMENT_SUMMARY:END -->

<!-- FASTLANE:HUMAN_VIEW:BEGIN -->
## What this record means

Fastlane keeps this explanation synchronized with the current project records.

### Defect picture

Defect status is No active bounded defect. User impact is None, and reproduction is Not active.

### Repair boundary

Root-cause status is Not active; repair status is Not active. Current owner action: Run `init template`. Next, Codex will verify prerequisites and initialize the project.
<!-- FASTLANE:HUMAN_VIEW:END -->

## 1. Summary

The first-screen status identifies the active defect, user impact, evidence,
repair state, and current project action.

<details>
<summary>Exact defect identity record</summary>

- Bug ID: BUG-001
- Title: TODO
- Severity: TODO
- Environment: TODO
- First observed: TODO
- Related GitHub Issue: TODO
- Related PRD requirements: TODO

</details>

## 2. Current behavior

TODO - the observable behavior, affected users, frequency, environment, supporting evidence, and any safe workaround.

## 3. Expected behavior

TODO - the correct observable result and its existing requirement basis. A repair does not silently add a feature.

## 4. Intentionally unchanged behavior

TODO - the public contracts, unrelated flows, data, permissions, performance,
and deployment behavior that the repair must preserve.

## 5. Reproduction

### Preconditions

- TODO

### Steps

1. TODO
2. TODO
3. TODO

### Actual result

TODO

### Expected result

TODO

## 6. Impact and risk

- User impact: TODO
- Security or privacy impact: TODO
- Data-integrity impact: TODO
- Reliability impact: TODO
- Cost impact: TODO
- Operational impact: TODO

## 7. Root-cause analysis

### Confirmed evidence

- TODO

### Hypotheses

| ID | Hypothesis | Evidence for | Evidence against | Status |
|---|---|---|---|---|
| HYP-001 | TODO | TODO | TODO | Open |

Do not present a hypothesis as confirmed root cause.

## 8. Fix constraints

- Allowed scope: TODO
- Out of scope: TODO
- Compatibility requirements: TODO
- Migration or rollback needs: TODO
- AWS resources affected: TODO

## 9. Regression and property specification

Fastlane adds repeatable checks that reproduce the defect and prove behavior
outside the approved repair remains unchanged.

<details>
<summary>Exact regression examples and generated-property records</summary>

### Example regression tests

| Test ID | Scenario | Expected result |
|---|---|---|
| REG-001 | Reproduction case | Expected behavior occurs |
| REG-002 | Unchanged neighboring behavior | Behavior remains unchanged |

### Properties

| Property ID | Invariant | Generated inputs or states | Oracle |
|---|---|---|---|
| BUG-PROP-001 | The reported failure cannot occur for any valid input in the affected domain. | TODO | TODO |
| BUG-PROP-002 | Intentionally unchanged behavior remains equivalent before and after the fix. | TODO | TODO |

</details>

## 10. Acceptance criteria

- [ ] Reproduction fails before the fix and passes after it
- [ ] Root cause is supported by evidence
- [ ] Expected behavior is restored
- [ ] Unchanged behavior remains unchanged
- [ ] Relevant property-based tests pass
- [ ] Security and failure paths are tested
- [ ] Rollback path is understood
- [ ] `docs/project/VERIFY.md` is updated with produced evidence
- [ ] `docs/project/TASKS.md` and the GitHub Issue are synchronized

## 11. Task references

- TASK-XXX — TODO
