# {{PROJECT_NAME}} — Bugfix Record

This document explains the active defect, its impact, the approved repair, and the proof that it works without changing unrelated behavior; when no defect is active, the current-state summary says so.
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
- [Acceptance criteria](#10-acceptance-criteria)
<!-- FASTLANE:DOCUMENT_SUMMARY:END -->

## 1. Summary

- Bug ID: BUG-001
- Title: TODO
- Severity: TODO
- Environment: TODO
- First observed: TODO
- Related GitHub Issue: TODO
- Related PRD requirements: TODO

## 2. Current behavior

TODO — Record the observable behavior, affected users, frequency, environment, evidence, and any known workaround.

## 3. Expected behavior

TODO — State the correct observable behavior and link existing requirements; a repair does not silently add a feature.

## 4. Intentionally unchanged behavior

TODO — Name the public contracts, unrelated flows, data formats, permissions, performance boundaries, and deployment behavior that the repair must preserve.

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

## 8. Fix constraints

- Allowed scope: TODO
- Out of scope: TODO
- Compatibility requirements: TODO
- Migration or rollback needs: TODO
- AWS resources affected: TODO

## 9. Regression and property specification

Fastlane uses repeatable checks to reproduce the defect, prove the expected behavior, and confirm that important neighboring behavior still works.

### Repeatable checks

| Test ID | Scenario | Expected result |
|---|---|---|
| REG-001 | Reproduction case | Expected behavior occurs |
| REG-002 | Unchanged neighboring behavior | Behavior remains unchanged |

### Broader safety checks

| Check ID | Rule that must always hold | Inputs or situations covered | How success is decided |
|---|---|---|---|
| BUG-PROP-001 | The reported failure cannot occur for any valid input in the affected domain. | TODO | TODO |
| BUG-PROP-002 | Intentionally unchanged behavior remains equivalent before and after the fix. | TODO | TODO |

## 10. Acceptance criteria

- [ ] Reproduction fails before the fix and passes after it
- [ ] Root cause is supported by evidence
- [ ] Expected behavior is restored
- [ ] Unchanged behavior remains unchanged
- [ ] Relevant broader safety checks pass
- [ ] Security and failure paths are tested
- [ ] Rollback path is understood
- [ ] The verification record contains the produced evidence
- [ ] The task record and any authorized GitHub issue agree

## 11. Task references

- TASK-XXX — TODO
