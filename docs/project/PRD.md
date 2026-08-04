# {{PROJECT_NAME}} — Product Requirements and Technical Design

Canonical path: `docs/project/PRD.md`.
<!-- FASTLANE:DOCUMENT_SUMMARY:BEGIN -->
## Current state

| Field | Current value |
|---|---|
| Product outcome | Not yet confirmed |
| First-release boundary | Not yet confirmed |
| Requirements | Not yet initialized |
| Technical design | Not yet initialized |
| Gate A | Not yet initialized |
| Gate B | Not yet initialized |
| Last completed milestone | None |
| Region and cost | Not yet recorded |
| Construction authorization | None |
| AWS account work | Not authorized |
| Current records | Not yet initialized |
| Updated | Not yet initialized |
| Need from you | Run `init template`. |
| Next | Codex will verify prerequisites and initialize the project. |

## Go directly to

- [Product Agreement](#product-agreement)
- [Gate A Review](#gate-a-review)
- [Technical Plan](#technical-plan)
- [Gate B Review](#gate-b-review)
- [Exact contract records](#contract-appendices)
<!-- FASTLANE:DOCUMENT_SUMMARY:END -->

## Current project state

This document owns the product agreement, technical plan, and both owner gates.
Read the current state above, then go directly to the section named by Fastlane.

- Gate A approves the product requirements.
- Gate B approves the technical plan and bounded local construction.
- AWS account work always remains separately authorized.

<details>
<summary>Exact document configuration and adaptive-coverage records</summary>

## Document status

| Field | Value |
|---|---|
| Bootstrap release | TODO (release version and source commit/tag) |
| Workflow mode | `codex-native` |
| Project contract schema | `1.4` |
| Project design contract schema | `7` |
| Project mode | `greenfield` / `brownfield` |
| Delivery profile | `quick-mvp` / `standard` / `high-risk` |
| Effective risk | `low` / `moderate` / `high` / `critical` |
| AWS lane | `documentation-only` / `read-only` / `fast-dev` / `explicit-gate` |
| Specification status | Draft |
| Current requirements revision | `REQ-0001` |
| Gate A derived status | `BLOCKED` |
| Current design revision | `DES-0001` |
| Current construction authorization ID | `AUTH-0001` |
| Gate B derived status | `BLOCKED` |
| Design status | Not started |
| Target release | TODO |
| Last reviewed | TODO |
| Primary owner | TODO |

### Delivery profile overlays

| Profile | Required overlay |
|---|---|
| `quick-mvp` | One thin, observable outcome; one development environment and Region where feasible; minimal independently verifiable tasks; one coordinator; explicit rollback or teardown. |
| `standard` | Intended-environment operations, integration and migration coverage, with serialized construction by one coordinator. |
| `high-risk` | Deeper review of identity, data access, customer separation, migration, recovery, rollback, shared-resource impact, audit needs, and failure handling; smaller mutation batches; stronger evidence. |

### Adaptive coverage plan

| Work kind | Delivery profile | Architecture disposition | Required sections | Omitted sections and reasons | Basis IDs |
|---|---|---|---|---|---|
| TODO | TODO | TODO | TODO | TODO | TODO |

</details>

# Product Agreement

## 1. Workload profile

| Field | Value |
|---|---|
| Workload | {{PROJECT_NAME}} |
| Business outcome | TODO |
| Primary owner | TODO |
| Users | TODO |
| Environment | Development / staging / production |
| AWS accounts | TODO |
| Primary Region | {{AWS_REGION}} |
| Data classification | Public / internal / confidential / regulated |
| Availability target | TODO |
| Recovery target | RTO: TODO; RPO: TODO |
| Cost posture | {{COST_POSTURE}} |
| Expected traffic | TODO |
| Applicable AWS lenses | TODO |

### Owner decisions and sources

Owner-confirmed selections stay in the exact intake record below. Expand it to
see each question, answer, and requirement basis without duplicated state.

<details>
<summary>Exact intake provenance and brownfield preservation records</summary>

### 1.1 Intake provenance

These records bind confirmed owner facts and observed repository facts without
storing raw conversation transcripts.

| Field | Value |
|---|---|
| Intake session ID | TODO |
| Intake source links | TODO (Notion page, issue, transcript, or `NONE`) |
| Participants and decision owner | TODO |
| Captured by | TODO |
| Captured at | TODO (ISO 8601 with timezone) |
| Last reconciled with sources | TODO (ISO 8601 with timezone) |
| Owner-stated outcome, in their words | TODO |
| Unresolved input IDs | TODO / `NONE` |
| Material source conflicts | TODO / `NONE` |

| Requirement or constraint ID | Basis | Source or evidence | Confidence | Owner confirmation |
|---|---|---|---|---|
| FR-001 | `OWNER_FACT` / `REPOSITORY_FACT` / `AGENT_RECOMMENDATION` / `PROPOSED_ASSUMPTION` / `OPEN_QUESTION` | TODO | TODO | TODO |

#### Intake foundation

| Intake ID | Field | Value | Basis | Status | Owner response |
|---|---|---|---|---|---|
| INTAKE-0001 | OWNER_WORK_CONTEXT | TODO | OPEN_QUESTION | OPEN | NONE |
| INTAKE-0002 | PRIMARY_USERS | TODO | OPEN_QUESTION | OPEN | NONE |
| INTAKE-0003 | OWNER_STATED_PROBLEM | TODO | OPEN_QUESTION | OPEN | NONE |
| INTAKE-0004 | OBSERVABLE_OUTCOME | TODO | OPEN_QUESTION | OPEN | NONE |
| INTAKE-0005 | FIRST_RELEASE_BOUNDARY | TODO | OPEN_QUESTION | OPEN | NONE |
| INTAKE-0006 | SUCCESS_MEASURE | TODO | OPEN_QUESTION | OPEN | NONE |
| INTAKE-0007 | DATA_TYPES | TODO | OPEN_QUESTION | OPEN | NONE |
| INTAKE-0008 | DATA_SENSITIVITY | TODO | OPEN_QUESTION | OPEN | NONE |
| INTAKE-0009 | RELEASE_AUDIENCE | TODO | OPEN_QUESTION | OPEN | NONE |
| INTAKE-0010 | OPERATING_GEOGRAPHY | TODO | OPEN_QUESTION | OPEN | NONE |

#### Normalized owner response register

| Owner response ID | Card ID | Revision | Presented card digest | Reply key | Question ID | Selection | Selection detail | Basis IDs |
|---|---|---|---|---|---|---|---|---|

#### Current intake decision card

| Card ID | Revision | Reply key | Question ID | Kind | Basis IDs | Prompt | Option A | Option B | Option C | Recommended | Required detail for | Detail prompt | Selection | Selection detail | Owner response |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| INTAKE-CARD-0001 | 1 | 1 | INTAKE-Q-0001 | DECISION | INTAKE-0001 | What are you starting with? | A new application; no existing product behavior is assumed. | A change to an existing application; preserve its users, data, and behavior unless you approve otherwise. | A repair, replacement, or migration; assess continuity and migration risk first. | NONE | B, C | Name the existing application or system. | PENDING | NONE | NONE |

### 1.2 Brownfield baseline and preservation contract

Complete these records only for brownfield work. Unknown behavior remains a
Gate A finding, never permission to replace it. List every existing application
source root exactly (for example, `service/**`) in both **Protected files and
components** and the matching `PRES-*` row so the technical plan can preserve
it without creating a parallel application folder.

| Field | Brownfield baseline |
|---|---|
| Repository and baseline commit | TODO |
| Deployed environments and observed versions | TODO |
| Existing architecture and ownership | TODO |
| Current interfaces, schemas, and consumers | TODO |
| Current data stores and migration constraints | TODO |
| Existing security and compliance controls | TODO |
| Baseline verification commands | TODO |
| Baseline evidence location | TODO |
| Known defects and accepted debt | TODO / `NONE_OBSERVED` |
| Repository-to-environment drift | TODO / `NONE_OBSERVED` |
| Dirty or user-owned working-tree changes | TODO / `NONE` |
| Protected files and components | TODO |
| Unresolved bootstrap overlay collisions | TODO / `NONE` |

| Preservation ID | Behavior, asset, or constraint to preserve | How it is verified before change | Allowed change | Explicitly prohibited or approval-required change |
|---|---|---|---|---|
| PRES-001 | TODO | TODO | TODO | TODO |

</details>

## Product requirements

## 2. Product statement

Describe the product, target user, and core value in one paragraph.

## 3. Problem and opportunity

Describe:

- the problem or deficiency;
- who experiences it;
- current impact or risk;
- why it is worth solving now.

## 4. Users and outcomes

| Actor ID | Actor or external system | Kind | Desired outcome or responsibility | Permission/data boundary | Intake basis IDs |
|---|---|---|---|---|---|
| ACT-001 | TODO | TODO | TODO | TODO | TODO |

`Kind` is exactly `PRIMARY_USER`, `SECONDARY_USER`, `OPERATOR`, or `EXTERNAL_SYSTEM`.

## 5. Goals and non-goals

### Goals

1. TODO
2. TODO
3. TODO

### Non-goals

- TODO
- TODO

## 6. Feature specifications

### User stories

| ID | User story | Priority | Related requirements |
|---|---|---|---|
| US-001 | As a TODO, I want TODO, so that TODO. | High | FR-001 |

### Functional requirements

| ID | Requirement | EARS form | Acceptance ID | Acceptance criteria | Acceptance form |
|---|---|---|---|---|---|
| FR-001 | TODO | UBIQUITOUS | AC-FR-001 | TODO | MEASURABLE |
| FR-002 | TODO | UNWANTED_BEHAVIOR | AC-FR-002 | TODO | GHERKIN |

<details>
<summary>Exact requirement grammar and compatibility</summary>

The six columns above are the **Fastlane EARS Contract** for normative
requirements; they do not redefine EARS outside this template. The EARS form
states one observable obligation and the acceptance form states how that
obligation is verified. A `MEASURABLE` row needs both an observable expected
result and a bound, policy/configuration check, exact command/API, or stable
`TEST-*`, `PROP-*`, or `EV-*` binding. Do not apply these fields to goals,
stories, facts, assumptions, decisions, architecture, tasks, tests, receipts,
or evidence. Replace undefined terms such as "fast," "secure," "large," or
"user friendly" with measurable conditions.

Compatibility is revision-bound. An unchanged approved schema 1.3 Gate A is
grandfathered until a requirements-controlled change. An unchanged approved
schema 1.2 Gate A remains the basis for a design-only move to schema 6. Codex completes generated design
records without rewriting Part I or asking the owner to repeat confirmed facts;
only a missing required owner fact returns to the owner. Unapproved schema 1.2
migrates before Gate A, while a requirements change requires schema 1.4 and
invalidates both gates. The design-only bridge derives `AC-<requirement ID>`
from approved acceptance rows; legacy `NEW_BUILD` uses journey `NONE` and binds
its end-to-end Harness to the wave plus every selected approved requirement.
Fastlane identifies migration rows and never invents owner requirements.

</details>

## 7. Primary, alternate, and failure flows

### Journey register

| Journey ID | Actor IDs | Goal | Trigger | Main success outcome | Alternate/failure behavior | Requirement IDs | Rich-use-case triggers |
|---|---|---|---|---|---|---|---|
| JOURNEY-001 | TODO | TODO | TODO | TODO | TODO | TODO | TODO |

Use only `DISTINCT_PERMISSIONED_ACTORS`,
`CONFIDENTIAL_OR_REGULATED_MUTATION`, `MONEY_OR_ENTITLEMENT`,
`IRREVERSIBLE_ACTION`, `MIGRATION_OR_CUTOVER`, `ASYNCHRONOUS_WORK`,
`PARTIAL_FAILURE`, or `NONE` in the final column.

Rich-use-case applicability is journey-specific. At low or moderate risk,
every journey with any trigger other than `NONE` requires a rich use case bound
to that same journey. At high or critical risk, every declared journey requires
one. The typed journey rows are authoritative; the applicability summary cannot
transfer a trigger to a different journey.

### Journey view

NOT_YET_CREATED - Codex adds a project-specific journey diagram only when the approved flow needs one.

### Rich-use-case applicability

| Applicability | Trigger basis | Use-case IDs |
|---|---|---|
| TODO | TODO | TODO |

### Rich use cases

| Use case ID | Journey ID | Primary actor ID | Stakeholder interests | Preconditions | Success guarantee | Minimum failure guarantee | Business rule IDs | Requirement IDs |
|---|---|---|---|---|---|---|---|---|

### Business rules

| Rule ID | Rule | Basis IDs | Journey/use-case IDs | Validation ID |
|---|---|---|---|---|
Optional Mermaid flow diagrams may illustrate a validated `JOURNEY-*` or
`STATE-*` record when they improve owner understanding. They are presentation
aids, not Gate A readiness artifacts; the existing journey and state records
remain authoritative.

### Alternate flows

- TODO

### Failure and recovery flows

- TODO

## 8. Data requirements

| ID | Requirement | EARS form | Acceptance ID | Acceptance criteria | Acceptance form |
|---|---|---|---|---|---|
| DATA-001 | The project SHALL identify exactly one authoritative store and accountable owner for each persistent data category. | UBIQUITOUS | AC-DATA-001 | A data-inventory check maps every persistent category to exactly one source of truth and one accountable owner. | MEASURABLE |
| DATA-002 | The project SHALL assign an approved classification and access boundary to each data category. | UBIQUITOUS | AC-DATA-002 | Access tests and configuration evidence show approved access succeeds and access outside each recorded boundary is denied. | MEASURABLE |
| DATA-003 | The project SHALL define retention, deletion, and audit-data behavior for every stored category. | UBIQUITOUS | AC-DATA-003 | Time-bounded tests or observed evidence demonstrate the approved retention, deletion, and audit outcomes for every stored category. | MEASURABLE |
| DATA-004 | WHERE durable recovery applies, the service SHALL restore data within the approved recovery objectives. | OPTIONAL_FEATURE | AC-DATA-004 | A timed restore rehearsal meets the current RTO and RPO, or the requirement records why durable recovery does not apply. | MEASURABLE |
| DATA-005 | WHILE data-bearing construction is planned, the design SHALL identify migration, compatibility, and residency constraints. | STATE_DRIVEN | AC-DATA-005 | A traceability check maps every applicable constraint to a validation, migration, or rollback check. | MEASURABLE |

## 9. Security and privacy requirements

| ID | Requirement | EARS form | Acceptance ID | Acceptance criteria | Acceptance form |
|---|---|---|---|---|---|
| SEC-001 | WHILE an operation is protected, the application SHALL permit only signed-in identities to perform it. | STATE_DRIVEN | AC-SEC-001 | GIVEN an approved protected operation, WHEN a signed-in or signed-out identity requests it, THEN the signed-in request succeeds and the signed-out request is denied. | GHERKIN |
| SEC-002 | The service SHALL enforce each identity's approved data and action boundary on the server. | UBIQUITOUS | AC-SEC-002 | Authorization tests prove approved access succeeds and unapproved access is denied at the recorded identity boundary. | MEASURABLE |
| SEC-003 | The project SHALL keep secrets outside source control, generated artifacts, and telemetry. | UBIQUITOUS | AC-SEC-003 | Secret scans pass and reviewed generated artifacts and logs contain zero secret values. | MEASURABLE |
| SEC-004 | IF external input violates documented shape or size limits, THEN the application SHALL reject it without creating an unintended change. | UNWANTED_BEHAVIOR | AC-SEC-004 | GIVEN invalid, malformed, or oversized external input, WHEN the application receives it, THEN the request is rejected and no unintended state change is recorded. | GHERKIN |
| SEC-005 | The deployment SHALL grant IAM and trust policies only the required actions on the required resources. | UBIQUITOUS | AC-SEC-005 | Policy checks and deployed access tests confirm required actions succeed and actions outside the approved resource boundary are denied. | MEASURABLE |
| SEC-006 | WHERE sensitive data is handled, the service SHALL use approved encryption controls in transit and at rest. | OPTIONAL_FEATURE | AC-SEC-006 | Infrastructure definitions and deployed configuration checks match every approved encryption control. | MEASURABLE |
| SEC-007 | WHEN an important access or change event occurs, the service SHALL record the actor, action, target, and time without recording secrets. | EVENT_DRIVEN | AC-SEC-007 | Audit-event tests and log review confirm all five required event conditions for every sampled event. | MEASURABLE |

Invalid, malformed, and oversized inputs are rejected without creating an
unintended change.

Remove rows that genuinely do not apply and add any workload-specific
safeguards needed for the approved users, data, and integrations. Record an
actual discovered defect in `docs/project/BUGFIX.md` or an authorized issue rather than in
generic template prose.

## 10. Reliability requirements

| ID | Requirement | EARS form | Acceptance ID | Acceptance criteria | Acceptance form |
|---|---|---|---|---|---|
| REL-001 | The service SHALL bound timeouts and retries to approved limits. | UBIQUITOUS | AC-REL-001 | Generated failure-sequence tests never exceed the configured timeout and retry bounds. | MEASURABLE |
| REL-002 | WHEN delivery repeats work, the service SHALL produce one effective outcome. | EVENT_DRIVEN | AC-REL-002 | GIVEN work that may be delivered more than once, WHEN the same work is delivered repeatedly, THEN one effective outcome is recorded. | GHERKIN |
| REL-003 | IF stale or concurrent work conflicts with newer state, THEN the service SHALL preserve the newer valid state without corruption. | UNWANTED_BEHAVIOR | AC-REL-003 | Stateful concurrency property tests preserve the newer valid state across the approved generated-case bound. | MEASURABLE |
| REL-004 | WHERE durable recovery applies, the service SHALL restore within the approved RTO and RPO. | OPTIONAL_FEATURE | AC-REL-004 | A timed restore rehearsal meets the approved RTO and RPO. | MEASURABLE |
| REL-005 | WHEN a release fails approved health checks, the deployment SHALL support rollback to the last known-good artifact. | EVENT_DRIVEN | AC-REL-005 | A rollback rehearsal restores the bound last known-good artifact and all approved smoke tests pass. | MEASURABLE |

## 11. Performance, cost, and sustainability requirements

### Performance efficiency

| ID | Requirement | EARS form | Acceptance ID | Acceptance criteria | Acceptance form |
|---|---|---|---|---|---|
| PERF-001 | The project SHALL define an explicit latency target and measurement condition for each critical user path. | UBIQUITOUS | AC-PERF-001 | Each target names the path, percentile or bound, workload, and observable test result. | MEASURABLE |
| PERF-002 | The project SHALL define expected throughput and concurrency for each approved environment. | UBIQUITOUS | AC-PERF-002 | A bounded test or calculation covers the approved normal and peak workload for every environment. | MEASURABLE |
| PERF-003 | The design SHALL define scaling boundaries and resource limits. | UBIQUITOUS | AC-PERF-003 | Tests or configuration checks show work stays within approved limits and fails safely at each boundary. | MEASURABLE |
| PERF-004 | WHERE performance evidence is required, the project SHALL document the load-test profile. | OPTIONAL_FEATURE | AC-PERF-004 | The profile records data shape, duration, concurrency, environment, and pass condition, or records why performance evidence does not apply. | MEASURABLE |

### Cost optimization

| ID | Requirement | EARS form | Acceptance ID | Acceptance criteria | Acceptance form |
|---|---|---|---|---|---|
| COST-001 | The project SHALL use `{{COST_POSTURE}}` and minimize expected total cost and idle spend while satisfying approved security, reliability, performance, and evidence requirements. | UBIQUITOUS | AC-COST-001 | The Gate A card, project state, and selected design use the same cost posture, and a traceability check finds no weakened approved requirement. | MEASURABLE |
| COST-002 | The project SHALL record any owner hard cap, budget-alert thresholds, and recipients without inventing a hard cap. | UBIQUITOUS | AC-COST-002 | The record contains the owner's exact cap and alert plan, or records `HARD_CAP_NOT_STATED` or why cost alerts do not apply. | MEASURABLE |
| COST-003 | The design SHALL identify primary cost drivers, expected low-usage cost, and scaling breakpoints. | UBIQUITOUS | AC-COST-003 | The design records material billing dimensions and an attributable estimate or current-source calculation. | MEASURABLE |
| COST-004 | WHEN expansion or migration is proposed, the design SHALL require a measurable approved trigger before the change. | EVENT_DRIVEN | AC-COST-004 | Each proposed expansion records a bounded threshold, evidence source, and owner decision path. | MEASURABLE |
| COST-005 | The project SHALL define tagging, idle-resource handling, and teardown expectations for created resources. | UBIQUITOUS | AC-COST-005 | IaC and runbook checks cover approved tags, idle policy, and teardown or retained-resource behavior. | MEASURABLE |

A hard cap is optional during requirements approval unless it is an owner-stated
business constraint. Do not manufacture one. Preserve a real cap in the Gate A
posture as `MINIMIZE_TOTAL_COST; HARD_CAP: <ISO_CURRENCY> <OWNER_AMOUNT>` using
the owner's exact currency and amount. For example, an owner-provided USD 20.00
cap becomes `MINIMIZE_TOTAL_COST; HARD_CAP: USD 20.00`. A finite positive Gate B
ceiling such as `USD: 20.00` is required before any AWS mutation or billable
deployed test, applies across that authorization's validity period, and cannot
exceed or change the currency of the Gate A cap. It is an authorization limit,
not a guaranteed provider-side billing stop. Never select a cheaper option by
weakening required identity, encryption, secrets handling, input validation,
isolation, recovery, logging, or evidence controls.

### Sustainability

| ID | Requirement | EARS form | Acceptance ID | Acceptance criteria | Acceptance form |
|---|---|---|---|---|---|
| SUS-001 | WHERE the approved workload does not need an idle resource, the deployment SHALL remove or scale down that resource. | OPTIONAL_FEATURE | AC-SUS-001 | Configuration or teardown evidence confirms the approved idle behavior for every applicable resource. | MEASURABLE |
| SUS-002 | The design SHALL avoid unnecessary data movement and retention. | UBIQUITOUS | AC-SUS-002 | A design review identifies material movement and retention and records a requirement basis for each retained path. | MEASURABLE |
| SUS-003 | WHEN capacity expansion is proposed, the project SHALL measure utilization before approving the expansion. | EVENT_DRIVEN | AC-SUS-003 | Expansion evidence cites the approved utilization trigger and an observed measurement at or above that trigger. | MEASURABLE |
| SUS-004 | WHEN learning changes an approved architecture decision, the project SHALL record the tradeoff and owner decision path. | EVENT_DRIVEN | AC-SUS-004 | A traceability check links the affected requirement and design IDs, evidence, and owner decision. | MEASURABLE |

## 12. Operational requirements

| ID | Requirement | EARS form | Acceptance ID | Acceptance criteria | Acceptance form |
|---|---|---|---|---|---|
| OPS-001 | The deployment SHALL define infrastructure and environments reproducibly through the approved IaC boundary. | UBIQUITOUS | AC-OPS-001 | IaC validation and environment-specific configuration checks pass for every approved environment. | MEASURABLE |
| OPS-002 | WHILE deployment is planned, the project SHALL define the deployment strategy and stop conditions. | STATE_DRIVEN | AC-OPS-002 | The runbook check confirms the artifact, order, health checks, failure boundary, and authorized next action are explicit. | MEASURABLE |
| OPS-003 | The service SHALL provide approved logs, metrics, dashboards, and alarms without exposing secrets. | UBIQUITOUS | AC-OPS-003 | Evidence checks confirm required signals, thresholds, destinations, and zero secret values in sampled content. | MEASURABLE |
| OPS-004 | The project SHALL identify incident ownership and an actionable escalation path. | UBIQUITOUS | AC-OPS-004 | The runbook check identifies one responsible owner and one actionable escalation path for each material incident class. | MEASURABLE |
| OPS-005 | The project SHALL define testable rollback and teardown behavior. | UBIQUITOUS | AC-OPS-005 | Rehearsal or observed evidence covers rollback, retained resources, and the approved teardown result. | MEASURABLE |

<details>
<summary>Exact quality-scenario and requirement-coverage records</summary>

### Quality attribute scenarios

| QAS ID | Requirement IDs | Source | Stimulus | Environment | Artifact | Response | Response measure |
|---|---|---|---|---|---|---|---|
| QAS-001 | TODO | TODO | TODO | TODO | TODO | TODO | TODO |

### Requirement coverage

| Requirement ID | Intake basis IDs | Actor IDs | Journey IDs | Acceptance/test IDs | Approved success measure ID |
|---|---|---|---|---|---|
| FR-001 | TODO | TODO | TODO | AC-FR-001 | INTAKE-0006 |

</details>

# Gate A Review

Gate A confirms the complete product agreement: outcome, users, first-release
scope, success measures, data and access boundaries, risk, recovery, Region,
and cost posture. It does not approve a technical design, construction,
publication, deployment, or teardown.

Review the readiness card, request a correction with
`Change the requirements: <correction>.`, or provide the exact receipt shown
last in the owner acceptance record. After approval, Codex continues to Design.

<details>
<summary>Exact Gate A analysis, lineage, assumptions, and open-decision records</summary>

## 13. Cross-requirement analysis

### Findings

| ID | Type | Requirements involved | Finding | Resolution or decision | Blocking? | Status |
|---|---|---|---|---|---|---|
| RA-001 | Ambiguity | TODO | TODO | TODO | Yes | Open |

### Requirements change lineage

| Current revision | Prior revision | Trigger | Added IDs | Changed IDs | Removed IDs | Preserved IDs | Stale reason | Required revalidation |
|---|---|---|---|---|---|---|---|---|
| REQ-0001 | NONE | INITIAL_DEFINITION | TODO | NONE | NONE | NONE | NONE - first definition | FULL_REVALIDATION |

### Assumption lifecycle

| Assumption ID | Assumption | Status | Basis IDs | Validation or successor |
|---|---|---|---|---|
| ASM-001 | TODO | PROPOSED | TODO | PENDING_OWNER_DECISION |

### Open decisions

| ID | Decision needed | Options | Decision owner | Blocking? | Resolution |
|---|---|---|---|---|---|
| DEC-001 | TODO | TODO | TODO | Yes | TODO |

### Gate A — agent analysis record

| Field | Agent-recorded value |
|---|---|
| Requirements revision analyzed | TODO |
| Reviewed commit (optional) | TODO / `NOT_RECORDED` |
| Analysis performed by | TODO |
| Analysis completed at | TODO (ISO 8601 with timezone) |
| Open blocking finding IDs | TODO / `NONE` |
| Proposed assumption IDs required to proceed | TODO / `NONE` |
| Open blocking decision IDs | TODO / `NONE` |
| AWS Core materiality | `REQUIRED` / `OPTIONAL` / `NOT_MATERIAL` |
| AWS materiality basis IDs | TODO (current REQ plus affected requirement IDs) / `NONE — <reason>` |
| AWS Core discovery IDs | TODO (current `AWS-DISC-*` IDs) / `NONE — <reason>` |
| Unresolved material AWS fact IDs | TODO (open `RA-*` / `DEC-*` IDs) / `NONE` |
| Agent recommendation | `BLOCKED` / `READY_WITH_PROPOSED_ASSUMPTIONS` / `READY_FOR_OWNER_APPROVAL` |
| Recommendation rationale | TODO |

</details>

### Gate A — readiness card

| Field | Current requirements decision basis |
|---|---|
| Outcome | TODO |
| Owner and users | TODO |
| Scope and non-goals | TODO |
| Measurable requirement/acceptance IDs | TODO |
| Data boundary | TODO |
| Identity/security boundary | TODO |
| Environment/Region | TODO |
| Failure/recovery | TODO |
| Cost posture | TODO (exactly `MINIMIZE_TOTAL_COST; HARD_CAP_NOT_STATED` or the owner's `MINIMIZE_TOTAL_COST; HARD_CAP: <ISO_CURRENCY> <OWNER_AMOUNT>`; `USD 20.00` is only an example) |
| Intake provenance | TODO |

### Gate A — owner acceptance record

| Field | Owner-provided value |
|---|---|
| Approver | TODO |
| Owner decision | `PENDING` / `CHANGES_REQUESTED` / `APPROVED` / `STALE` |
| Authorized requirements revision | TODO |
| Authorized cost posture | TODO (must exactly match the approved Gate A readiness card) |
| Explicitly accepted assumption IDs | TODO / `NONE` |
| Explicitly rejected assumption IDs and resolution | TODO / `NONE` |
| Authorization provided at | TODO (ISO 8601 with timezone) |
| Authorization source | TODO (message, issue, meeting record, or commit link) |
| Verbatim owner receipt | `RECORDED_BELOW` / `TODO` |
| Derived Gate A state | `BLOCKED` / `PENDING_OWNER_APPROVAL` / `APPROVED_FOR_DESIGN` / `STALE` |

<details>
<summary>Exact Gate A validation and invalidation rules</summary>

### Gate A validation and invalidation rules

The Engine requires a complete current product agreement, resolved blockers,
explicit AWS materiality, and the owner's exact matching receipt.

</details>

For approval, the owner receipt must use this human-readable form with actual
values substituted:

<!-- bootstrap:gate-a-receipt:start -->
```text
APPROVE REQUIREMENTS GATE A
Requirements revision: <REQ-nnnn>
Cost posture: <exact-Gate-A-cost-posture>
Accepted assumptions: <assumption-IDs-or-NONE>
Approver: <name/handle>
```
<!-- bootstrap:gate-a-receipt:end -->


# Technical Plan

Complete this part only after Gate A is valid.

### Technology decisions

The Gate B brief explains these selections in plain language. Expand the exact
records below when you want the complete source tables and candidate analysis.

<details>
<summary>Exact design revision, technology, driver, and candidate records</summary>

### Technical design revision record

| Field | Value |
|---|---|
| Current design revision | `DES-0001` |
| Requirements revision designed | TODO |
| Reviewed commit (optional) | TODO / `NOT_RECORDED` |
| Design prepared by | TODO |
| Design completed at | TODO (ISO 8601 with timezone) |
| Remaining design gaps | TODO / `NONE` |

### Technology and toolchain decision register

| Decision ID | Concern | Selection | Version policy | Source | Basis IDs | Alternatives and rationale | Compatibility/migration | Validation |
|---|---|---|---|---|---|---|---|---|
| TECH-0001 | APPLICATION_RUNTIME | TODO | TODO | TODO | TODO | RATIONALE: TODO; REJECTED: TODO | TODO | TODO |
| TECH-0002 | APPLICATION_FRAMEWORK | TODO | TODO | TODO | TODO | RATIONALE: TODO; REJECTED: TODO | TODO | TODO |
| TECH-0003 | FRONTEND_FRAMEWORK | TODO | TODO | TODO | TODO | RATIONALE: TODO; REJECTED: TODO | TODO | TODO |
| TECH-0004 | INFRASTRUCTURE_AS_CODE | TODO | TODO | TODO | TODO | RATIONALE: TODO; REJECTED: TODO | TODO | TODO |
| TECH-0005 | PACKAGE_BUILD_TOOLING | TODO | TODO | TODO | TODO | RATIONALE: TODO; REJECTED: TODO | TODO | TODO |
| TECH-0006 | TEST_TOOLING | TODO | TODO | TODO | TODO | RATIONALE: TODO; REJECTED: TODO | TODO | TODO |
| TECH-0007 | PROPERTY_TESTING | TODO | TODO | TODO | TODO | RATIONALE: TODO; REJECTED: TODO | TODO | TODO |
| TECH-0008 | SECURITY_VALIDATION | TODO | TODO | TODO | TODO | RATIONALE: TODO; REJECTED: TODO | TODO | TODO |
| TECH-0009 | DEPLOYMENT_TOOLING | TODO | TODO | TODO | TODO | RATIONALE: TODO; REJECTED: TODO | TODO | TODO |
| TECH-0010 | IDENTITY_AUTHORIZATION | TODO | TODO | TODO | TODO | RATIONALE: TODO; REJECTED: TODO | TODO | TODO |
| TECH-0011 | DATA_STORAGE | TODO | TODO | TODO | TODO | RATIONALE: TODO; REJECTED: TODO | TODO | TODO |
| TECH-0012 | MESSAGING_RETRIES | TODO | TODO | TODO | TODO | RATIONALE: TODO; REJECTED: TODO | TODO | TODO |
| TECH-0013 | EDGE_NETWORKING | TODO | TODO | TODO | TODO | RATIONALE: TODO; REJECTED: TODO | TODO | TODO |
| TECH-0014 | OBSERVABILITY_INCIDENT_RESPONSE | TODO | TODO | TODO | TODO | RATIONALE: TODO; REJECTED: TODO | TODO | TODO |
| TECH-0015 | RELIABILITY_RECOVERY | TODO | TODO | TODO | TODO | RATIONALE: TODO; REJECTED: TODO | TODO | TODO |

### Architecture drivers

| Driver ID | Requirement basis | Class | Decision implication | Validation |
|---|---|---|---|---|
| DRV-0001 | TODO | TODO | TODO | TODO |

### Whole-system candidates

| Candidate ID | Architecture summary | Requirement coverage | AWS evidence | Eligibility | Failed constraints | Tradeoffs |
|---|---|---|---|---|---|---|
| CAND-0001 | TODO | TODO | TODO | TODO | TODO | TODO |

</details>

### Selected architecture

| Architecture ID | Selected candidate | Requirement and driver basis | Rationale | Rejected alternatives | Risks | Mitigations | Security impact | Reliability impact | Operational burden | Cost effect | Breakpoints | Migration path | Revisit triggers | Validation |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ARCH-0001 | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO |

<details>
<summary>Exact architecture traceability, AWS evidence, change, and diagram bindings</summary>

### Architecture traceability

| Requirement ID | ARCH / API / EVENT / CLI / FILE / BOUNDARY / STATE IDs | Property/test IDs | Evidence IDs |
|---|---|---|---|
| TODO | TODO | TODO | TODO |

### Material AWS evidence

| Evidence ID | Discovery ID | Design IDs | Material claim | AWS Core capability | Official reference | Observed date |
|---|---|---|---|---|---|---|
| AWS-EV-0001 | AWS-DISC-0002 | TODO | TODO | `retrieve_skill` | TODO | TODO |
| AWS-EV-0002 | AWS-DISC-0002 | TODO | TODO | `search_documentation` | TODO | TODO |

### Change impact record

| Change ID | Changed basis IDs | Affected IDs | Preserved IDs | Required revalidation |
|---|---|---|---|---|
| CHANGE-0001 | TODO | TODO | TODO | TODO |

### Project diagram contract

| Diagram ID | Kind | Applicability | Status | Anchor | Basis IDs | Referenced IDs |
|---|---|---|---|---|---|---|
| DIAGRAM-0001 | SYSTEM_CONTEXT | REQUIRED | NOT_YET_CREATED | proposed-system-at-a-glance | NONE | NONE |
| DIAGRAM-0002 | PRIMARY_OUTCOME | REQUIRED | NOT_YET_CREATED | sequence-primary-outcome | NONE | NONE |
| DIAGRAM-0003 | DATA_LIFECYCLE | CONDITIONAL | NOT_YET_CREATED | data-lifecycle-view | NONE | NONE |
| DIAGRAM-0004 | FAILURE_RECOVERY | CONDITIONAL | NOT_YET_CREATED | sequence-failure-and-recovery | NONE | NONE |
| DIAGRAM-0005 | MIGRATION | CONDITIONAL | NOT_YET_CREATED | migration-view | NONE | NONE |
| DIAGRAM-0006 | JOURNEY | CONDITIONAL | NOT_YET_CREATED | journey-view | NONE | NONE |
| DIAGRAM-0007 | STATE | CONDITIONAL | NOT_YET_CREATED | state-view | NONE | NONE |

These records bind the selected architecture to current requirements and
sources. Diagrams describe planned design; only semantic changes affect the
design digest and stale Gate B.

</details>

### Migration view

NOT_YET_CREATED - Codex adds a project-specific migration diagram only when brownfield or migration work makes it material.

## 14. Architecture overview

### Proposed system at a glance

NOT_YET_CREATED - After Gate A, Codex replaces this slot with the selected
project architecture. The diagram uses canonical record IDs as Mermaid node
identifiers and plain-language labels. It expresses intended design only;
implementation and deployment proof belongs in code, tests, IaC, and VERIFY.

Describe the selected components, trust and identity boundaries, data movement,
external dependencies, and failure boundaries in the written design below.

## 15. Component design

| Component | Responsibility | Inputs | Outputs | Dependencies | Failure behavior | Owner |
|---|---|---|---|---|---|---|
| TODO | TODO | TODO | TODO | TODO | TODO | TODO |

### Layer boundaries

| Boundary ID | Outer adapter/layer | Inner domain layer | Boundary DTO/schema | Explicit mapping | Dependency direction | Authorization enforcement | External anti-corruption adapter | Requirement IDs | Validation IDs |
|---|---|---|---|---|---|---|---|---|---|
| BOUNDARY-001 | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO |

Applicable boundaries use explicit DTO/schema mapping, `INWARD` dependencies, and server-side authorization.

## 16. Interfaces and contracts

| Contract ID | Kind | Requirement basis | Producer | Consumer | Schema or protocol | Authentication | Authorization | Input validation | Success output/status | Error and recovery behavior | Compatibility/versioning | Idempotency/concurrency | Timeout bound | Rate bound | Performance bound |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| API-001 | API | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO |

Put schemas in code. Authorization is server-side or `NOT_APPLICABLE - <reason>`; timeout, rate, and performance use a numeric measurable bound or that sentinel.

## 17. Data model and lifecycle

### State-model applicability

Use ordered `CATEGORY: ID, ID; CATEGORY: ID`: `LIFECYCLE_RESOURCE`, `ASYNCHRONOUS_WORK`, `RETRY_OR_RESUME`,
`APPROVAL_FLOW`, `MIGRATION_OR_CUTOVER`, `OTHER_MEANINGFUL_TRANSITION`. Applicable categories bind `STATE-*`; non-applicable uses a reason and IDs `NONE`.

| Subject ID | Applicability | Trigger basis IDs | State model IDs |
|---|---|---|---|
| RESOURCE-001 | TODO | TODO | TODO |

### State register

| State model ID | Subject ID | States | Initial state | Allowed transitions | Terminal states | Invalid-transition behavior | Requirement IDs | Validation IDs |
|---|---|---|---|---|---|---|---|---|
| STATE-001 | RESOURCE-001 | TODO | TODO | TODO | TODO | TODO | TODO | TODO |

### State view

NOT_YET_CREATED - Codex adds a project-specific state diagram only when a meaningful lifecycle contract requires one.

### Data lifecycle view

NOT_YET_CREATED - Codex adds this project-specific view when approved data,
retention, deletion, backup, or recovery requirements make it material.

Define:

- entities and ownership;
- keys and indexes;
- consistency needs;
- transaction boundaries;
- retention;
- backup and restore;
- deletion semantics;
- concurrency controls.

## 18. Detailed sequence diagrams

### Sequence — primary outcome

NOT_YET_CREATED - Codex adds the selected application's primary end-to-end
outcome after its components and interfaces have canonical IDs.

### Sequence — failure and recovery

NOT_YET_CREATED - Codex adds the selected application's failure and recovery
flow when current reliability, asynchronous, or recovery records require it.

Replace required slots with project-specific diagrams. Keep each canonical block
at its bound anchor. Add an optional view only when it materially improves owner
understanding and its canonical records justify it.

## 19. Error handling strategy

| Error class | Example | Retry? | User-visible behavior | Logging or metric | Recovery |
|---|---|---|---|---|---|
| Validation | TODO | No | Safe 4xx or equivalent | Counter without sensitive input | User corrects request |
| Transient dependency | TODO | Bounded | Safe temporary failure | Error metric and correlation ID | Retry or queue |
| Permanent dependency | TODO | No | Reviewable terminal state | Alarm | Manual remediation |
| Concurrency conflict | TODO | No or retry with fresh state | Conflict response | Conflict metric | Re-read and retry |
| Internal defect | TODO | No uncontrolled retry | Generic safe error | Alert and trace | Rollback or fix |

Define error taxonomy, safe messages, correlation IDs, retry ownership, timeout ownership, dead-letter behavior, and operator actions.

## 20. AWS implementation approach

| Concern | Decision IDs | AWS service or mechanism | Rationale | Tradeoff |
|---|---|---|---|---|
| Compute | TODO | TODO | TODO | TODO |
| Identity | TODO | TODO | TODO | TODO |
| Data | TODO | TODO | TODO | TODO |
| Messaging or orchestration | TODO | TODO | TODO | TODO |
| Networking | TODO | TODO | TODO | TODO |
| Observability | TODO | TODO | TODO | TODO |
| Deployment | TODO | TODO | TODO | TODO |
| Secrets and encryption | TODO | TODO | TODO | TODO |

Reference the authoritative `TECH-*` rows in the `Decision IDs` column; do not
restate or override their selections or version policies here.

Use the installed `aws-core` plugin from Agent Toolkit for AWS and current AWS
primary documentation when completing this section. Compare the secure
serverless baseline with any proposed alternative using workload fit, required
controls, expected low-usage cost, scaling breakpoints, operational ownership,
and migration or expansion triggers. Cost never overrides a required security
or recovery control.

### Lightweight Well-Architected decision review

Keep this a short, blame-free design conversation, not a separate audit or
gate. Record the applicable Operational Excellence, Security, Reliability,
Performance Efficiency, Cost Optimization, and Sustainability effects in the
existing design and task records. Reversible low-risk choices need only concise
rationale. Expand evidence, alternatives, rollback, and owner visibility when
effective risk is high/critical or a decision is a one-way door that would be
difficult, costly, or unsafe to reverse.

## 21. Implementation boundaries and order

- Existing components to reuse: TODO
- Components to modify: TODO
- Components to add: TODO
- Compatibility constraints: TODO
- Migration approach: TODO
- Feature flags or staged rollout: TODO
- Rollback boundary: TODO
- Explicitly deferred work: TODO
### First construction wave

| Wave contract ID | Work kind | Walking-skeleton journey ID | Requirement IDs | Acceptance/test IDs | End-to-end Harness ID | Blocking spike ID |
|---|---|---|---|---|---|---|
| WAVE-0001 | TODO | TODO | TODO | TODO | TODO | NONE |

For `NEW_BUILD`, this row selects one tested end-to-end first-release outcome.
Its first structural task is the only first-wave task unless the bounded spike
below is explicitly approved.

### Blocking spike

| Spike ID | Blocking technical unknown | Time box | Disposable output boundary | Exit criterion | Required next action |
|---|---|---|---|---|---|
| SPIKE-0001 | TODO | TODO | TODO | TODO | DISCARD_AND_BUILD_WALKING_SKELETON |

Replace this table with `NOT_APPLICABLE — no prerequisite discovery is needed before the walking skeleton`
when no spike is needed. A spike records learning only and cannot satisfy the
approved product outcome.


<details>
<summary>Exact task-projection rule</summary>

The Engine derives tasks and requirement coverage from the approved design.

</details>

## Validation strategy

## 22. Test layers

| Layer | Purpose | Required coverage |
|---|---|---|
| Static | Formatting, linting, typing, schemas, IaC | TODO |
| Unit | Isolated rules and functions | TODO |
| Integration | Data stores, queues, identity, APIs, contracts | TODO |
| End-to-end | Complete user outcomes | TODO |
| Security | Authentication, authorization, abuse, secrets | TODO |
| Reliability | Retry, timeout, idempotency, concurrency, recovery | TODO |
| Performance | Latency, throughput, saturation, scaling | TODO |
| AWS environment | Deployed configuration and service behavior | TODO |
| Operations | Deployment, alarms, rollback, restore, teardown | TODO |

<details>
<summary>Exact Gate B Harness Profile</summary>

### Gate B Harness Profile

| Harness ID | Layer | Selected check or tool | Trigger | Basis IDs | Exact command or API | Evidence destination | Required or conditional status |
|---|---|---|---|---|---|---|---|
| HARNESS-001 | Static | TODO | TODO | TODO | TODO | docs/project/VERIFY.md#harness-execution-evidence | TODO |
| HARNESS-002 | Unit | TODO | TODO | TODO | TODO | docs/project/VERIFY.md#harness-execution-evidence | TODO |
| HARNESS-003 | Integration | TODO | TODO | TODO | TODO | docs/project/VERIFY.md#harness-execution-evidence | TODO |
| HARNESS-004 | End-to-end | TODO | TODO | TODO | TODO | docs/project/VERIFY.md#harness-execution-evidence | TODO |
| HARNESS-005 | Property | TODO | TODO | TODO | TODO | docs/project/VERIFY.md#harness-execution-evidence | TODO |
| HARNESS-006 | Security and privacy | TODO | TODO | TODO | TODO | docs/project/VERIFY.md#harness-execution-evidence | TODO |
| HARNESS-007 | Reliability and recovery | TODO | TODO | TODO | TODO | docs/project/VERIFY.md#harness-execution-evidence | TODO |
| HARNESS-008 | Performance and scalability | TODO | TODO | TODO | TODO | docs/project/VERIFY.md#harness-execution-evidence | TODO |
| HARNESS-009 | IaC and policy | TODO | TODO | TODO | TODO | docs/project/VERIFY.md#harness-execution-evidence | TODO |
| HARNESS-010 | AWS environment and operations | TODO | TODO | TODO | TODO | docs/project/VERIFY.md#harness-execution-evidence | TODO |
| HARNESS-011 | End-to-end | TODO | TODO | TODO | TODO | docs/project/VERIFY.md#harness-execution-evidence | TODO |
| HARNESS-012 | End-to-end | TODO | TODO | TODO | TODO | docs/project/VERIFY.md#harness-execution-evidence | TODO |
| HARNESS-013 | Unit | TODO | TODO | TODO | TODO | docs/project/VERIFY.md#harness-execution-evidence | TODO |
| HARNESS-014 | Static | TODO | TODO | TODO | TODO | docs/project/VERIFY.md#harness-execution-evidence | TODO |
| HARNESS-015 | Security and privacy | TODO | TODO | TODO | TODO | docs/project/VERIFY.md#harness-execution-evidence | TODO |
| HARNESS-016 | Property | TODO | TODO | TODO | TODO | docs/project/VERIFY.md#harness-execution-evidence | TODO |

The selected checks, triggers, commands, basis IDs, and evidence destinations
must be complete before Gate B. Fastlane does not impose a universal tool set.

</details>

<details>
<summary>Exact infrastructure and delivery validation contract</summary>

### IaC and delivery validation contract

Select validation from the approved `INFRASTRUCTURE_AS_CODE`,
`SECURITY_VALIDATION`, and `DEPLOYMENT_TOOLING` `TECH-*` rows; do not impose a
universal scanner. Mark unused paths `NOT_APPLICABLE — <reason>`.

| Validation path | Applicability | TECH binding | Required local/static validation | AWS planning validation | Evidence destination |
|---|---|---|---|---|---|
| CloudFormation / SAM / CDK | TODO | TODO | Synth or template validation, selected lint, and selected Guard or policy checks | Review an authorized existing change set; creating one is an AWS mutation | `docs/project/VERIFY.md` IaC validation evidence |
| Terraform | TODO | TODO | Formatting, validation, selected policy checks, and a deterministic plan boundary | Bind the reviewed plan to exact inputs, state/refresh mode, target, and digest | `docs/project/VERIFY.md` IaC validation evidence |
| Container delivery | TODO | TODO | Dependency/lock validation, SBOM generation, and selected image/configuration checks | Bind the immutable image digest and deployment target | `docs/project/VERIFY.md` IaC validation evidence |
| Other approved delivery path | TODO | TODO | Exact equivalent checks selected by current TECH decisions | Exact equivalent immutable plan and target binding | `docs/project/VERIFY.md` IaC validation evidence |

CloudFormation `CreateChangeSet` creates account-side state, including a
`REVIEW_IN_PROGRESS` stack for a new-stack change set, so it requires exact AWS
mutation authority even though `ExecuteChangeSet` is a separate operation.
Record both operations separately when both are allowed. An authenticated IAM
Access Analyzer `ValidatePolicy` call belongs only to AWS-10 after Gate B under
the named read-only scope. Local checks and unauthenticated documentation do not
substitute for either observation.

</details>

## 23. Example-based scenarios

| Test ID | Scenario | Expected result | Layer |
|---|---|---|---|
| EX-001 | Known happy path | TODO | Integration |
| EX-002 | Known boundary or failure | TODO | Unit |

<details>
<summary>Exact example-scenario record rules</summary>

Every `EX-*` referenced by architecture traceability or another current design
record appears exactly once in this table with a concrete scenario, expected
result, and layer. The complete Example-based scenarios table is
design-controlled and participates in the modern design digest after the
Technology decision register and before Property applicability, Property
definitions, and Property execution. Exact approved schema 4 designs retain
their grandfathered digest path.

</details>

## 24. Property-based testing specification

During DESIGN-10, classify every measurable Gate A requirement in the approved
revision exactly once. Use `APPLICABLE` only when a generated input or state
space and a stable oracle can test an invariant; otherwise record
`NOT_APPLICABLE` with a concrete reason.
Property-based testing is optional until an invariant is classified as
applicable. Every approved `PROP-*` is then required construction and release
evidence unless a later owner-approved requirements or design revision removes
or replaces it.

Every applicable property definition must contain concrete inputs, conditions,
oracle, boundaries, and layer. `NONE`, `PENDING`, `PLACEHOLDER`, and similar
sentinels are not definitions.

| Requirement ID | Applicability | Reason or property IDs |
|---|---|---|
| TODO | `APPLICABLE` / `NOT_APPLICABLE` | TODO |

| Property ID | Requirement IDs | Invariant | Generated inputs or state | Preconditions | Oracle | Boundary or shrink focus | Layer |
|---|---|---|---|---|---|---|---|
| PROP-001 | SEC-002 | An actor never observes another actor's protected resource. | Actors, resources, roles, identifiers | Valid authenticated actors | Access allowed only when policy relation holds | Cross-tenant IDs, missing ownership, role changes | Integration |
| PROP-002 | REL-002 | Repeating the same event produces one effective state transition. | Duplicate counts, orderings, retry timing | Same idempotency identity | Final state and side effects equal one delivery | Reordered and repeated events | Integration |
| PROP-003 | SEC-003 | No generated secret appears in emitted telemetry. | Secret-like values and payload positions | Telemetry enabled | Search of logs/events contains no secret | Unicode, long values, encoded forms | Unit / integration |
| PROP-004 | REL-001 | Retry attempts never exceed the configured bound. | Failure sequences and transient/permanent classifications | Dependency fails | Attempts <= configured maximum | Zero, one, maximum, permanent transition | Unit |
| PROP-005 | TODO | TODO | TODO | TODO | TODO | TODO | TODO |

<details>
<summary>Exact property-execution records</summary>

### Property execution contract

| Property ID | Framework TECH ID | Exact command | Run target/time bound | Seed or reproduction format | Evidence destination |
|---|---|---|---|---|---|
| PROP-001 | TODO | TODO | TODO | TODO | TODO |

Each applicable property binds one approved framework decision, exact command,
run bound, replay format, and evidence destination. Observed results belong in
`docs/project/VERIFY.md`.

</details>

## 25. Test data and environments

- Synthetic fixture strategy: TODO
- Generated data constraints: TODO
- Sensitive-data prohibition: TODO
- Local emulation or mocks: TODO
- AWS test environment: TODO
- Cleanup strategy: TODO
- Cost limit for billable deployed tests: TODO / `NOT_APPLICABLE — local or documentation-only validation`

## 26. Release acceptance

Release is acceptable when:

- primary, alternate, and failure flows work;
- requirements-analysis blockers are resolved;
- architecture and interfaces are implemented as approved;
- required example and property-based tests pass;
- security and reliability evidence passes;
- deployment, monitoring, rollback, recovery, and cleanup are verified;
- `docs/project/VERIFY.md` records the exact release decision and remaining gaps.

<details>
<summary>Exact release-state and AWS evidence rules</summary>

The release lifecycle is `NOT_READY` -> `READY_TO_DEPLOY` ->
`RELEASE_VERIFIED`. RELEASE-10 is the only prompt that changes this state.
AWS-10 starts only from READY_TO_DEPLOY. Before each AWS-20 mutation call,
`docs/project/VERIFY.md` receives an append-only STARTED row, followed by one
terminal direct-result row and an AWS-30 read-only reconciliation row for the
same Attempt ID. Each row preserves immutable deployment authority and
provenance: explicit-gate derives them from its deployment receipt; fast-dev
stores the exact current construction `AUTH-*`, derives its expiry timestamp
from Gate B `AWS authorization validity`, and uses Gate B's authorization source. Non-STARTED operation evidence uses the canonical unique-
identifiers/direct-result grammar; that structure alone never proves execution.
STARTED is not proof of a call. A lone STARTED is completed by Codex as UNKNOWN
before any owner action or AWS-30 read authorization request. Deployment
authority binds one attempt and never supplies AWS-30 read authority or permits
replay. FAILED, PARTIAL, and UNKNOWN require reconciliation before retry;
COMPLETE or BLOCKED
returns to RELEASE-10 for the final decision. One first STALE remains at AWS-30
and may be followed by one later COMPLETE or BLOCKED under a different current
read authorization. A repeated STALE is a safety-review blocker, and no
reconciliation row follows COMPLETE or BLOCKED. COMPLETE acceptance IDs must
satisfy VERIFY's exact current `VERIFIED` matrix-row and target-binding contract.
RELEASE-10 records the terminal
AWS-30 Evidence ID as VERIFY's Active evidence cutoff while deciding NOT_READY,
RELEASE_VERIFIED, or a separately authorized correction path. That acknowledgment
prevents rerouting the same attempt. Retry requires distinct current mutation
authority: a new exact deployment receipt for explicit-gate or freshly approved
construction authorization for fast-dev, plus a new Attempt ID.

</details>

# Gate B Review

Gate B approves the complete technical plan and a bounded local construction
run. It does not authorize GitHub publication or any AWS account operation.

## Executive decision

Review the recommendation, tradeoffs, evidence limits, construction boundary,
and what remains unauthorized. Request a correction with
`Change the design: <correction>.` or provide the exact receipt shown last in
the owner authorization record. After approval, Codex creates tasks and builds
locally inside the approved envelope.

## Technical decision index

| Concern | Owner-facing source |
|---|---|
| Application and runtime | [Selected architecture](#selected-architecture) and [component design](#15-component-design) |
| Identity and data | [Interfaces](#16-interfaces-and-contracts), [data lifecycle](#17-data-model-and-lifecycle), and [AWS approach](#20-aws-implementation-approach) |
| Reliability and operations | [Error handling](#19-error-handling-strategy), [release acceptance](#26-release-acceptance), and current project diagrams |
| Validation and construction | [Validation strategy](#validation-strategy), readiness card, and the exact construction envelope |

<details>
<summary>Exact Gate B agent review record</summary>

## 27. Gate B agent review record

| Field | Agent-recorded value |
|---|---|
| Requirements revision reviewed | TODO |
| Design revision reviewed | TODO |
| Construction authorization ID reviewed | TODO |
| Construction envelope SHA-256 reviewed | TODO (`sha256:` plus 64 lowercase hex characters) |
| Reviewed commit (optional) | TODO / `NOT_RECORDED` |
| PRD completeness gaps | TODO / `NONE` |
| Requirement-to-design-and-test traceability gaps | TODO / `NONE` |
| Unresolved risk or preservation gaps | TODO / `NONE` |
| Review completed by and at | TODO (identity and ISO 8601 time) |
| Agent recommendation | `BLOCKED` / `READY_FOR_CONSTRUCTION_APPROVAL` |
| Recommendation rationale | TODO |

</details>

### Gate B — readiness card

<details>
<summary>Exact Gate B readiness rules</summary>

The Engine blocks Gate B until every field and applicable Harness check is complete.

</details>

| Field | Current design and construction decision basis |
|---|---|
| Design basis IDs | TODO |
| Architecture/components | TODO |
| Technology/toolchains/version policy | TODO |
| Interfaces/data flow | TODO |
| Identity/secrets | TODO |
| Failure/retry/concurrency | TODO |
| Deployment/operations | TODO |
| Validation/evidence | TODO (cite required and triggered conditional `HARNESS-*` IDs) |
| Rollback/recovery/teardown | TODO |
| Brownfield compatibility/migration | TODO |
| Outstanding gaps | TODO / `NONE` |

## Construction and authorization boundary

Gate B authorizes only the exact local construction scope recorded below. It
does not authorize GitHub publication or AWS account work. Any broader path,
command, task, external target, cost, or operation requires the existing
correction and authorization process. The **Application source disposition**
names the one application-code home: `app/**` for greenfield work, the recorded
preserved roots for brownfield work, or an explicit infrastructure-only
exception. Fastlane rejects parallel greenfield `apps/**` and `src/**` roots.

<details>
<summary>Exact construction envelope and validation grammar</summary>

## 28. Construction envelope

| Boundary | Authorized value |
|---|---|
| Construction authorization ID | `AUTH-0001` |
| Project mode | `greenfield` / `brownfield` |
| Delivery profile and effective risk | `<profile> / <risk>` |
| Project AWS lane | `documentation-only` / `read-only` / `fast-dev` / `explicit-gate` |
| Authorized outcome | TODO |
| Authorized requirement and design IDs | `REQ: REQ-0001; DES: DES-0001; SCOPE_IDS: FR-001, SEC-001, ARCH-0001, TECH-0001, TECH-0002, TECH-0003, TECH-0004, TECH-0005, TECH-0006, TECH-0007, TECH-0008, TECH-0009, TECH-0010, TECH-0011, TECH-0012, TECH-0013, TECH-0014, TECH-0015, PROP-001, HARNESS-001` |
| Design contract SHA-256 | TODO (exact current `design_contract.canonical_sha256`) |
| Authorized baseline commit | TODO (full Git commit hash) |
| Protected dirty paths | `NONE` / `PATHS: path; path` |
| In-scope components and environments | TODO |
| Allowed repository write set | `PATHS: exact/path; narrow/**` |
| Excluded or owner-only write set | `NONE` / `PATHS: exact/path; narrow/**` |
| Application source disposition | `GREENFIELD_APP_ROOT: app/**` / `BROWNFIELD_PRESERVE: path/**; another/path/**` / `NOT_APPLICABLE — INFRASTRUCTURE_ONLY` |
| Allowed external-state targets | `NONE` / `TARGETS: exact-target; exact-target` |
| Task boundary | `DERIVED_FROM_AUTHORIZED_IDS_AND_WRITE_SET` / `TASK_IDS: TASK-0001, TASK-0002` |
| Maximum generated tasks | TODO (positive integer) |
| Eligible task status | `READY` |
| Autonomous construction | `ALLOWED` / `PROHIBITED` |
| Maximum parallel workers | `1` (v1 compatibility field; parallel writing is excluded) |
| Parallelism rule | One coordinator is the sole writer; tasks execute serially |
| Attempt budget | TODO (maximum implementation-validation cycles per task before stopping) |
| Checkpoint cadence | `COMMIT_AFTER_EACH_VALIDATED_WAVE_BEFORE_PAUSE` |
| Required checkpoint contents | Task status, changed paths, commands/evidence, commit, last-known-green, blockers, next safe action |
| Local command boundary | `ALLOW_PREFIXES: prefix; prefix` |
| GitHub boundary | `NONE` / `READ_ONLY` / `ISSUES` / `BRANCH_AND_PR` / `MERGE_WHEN_GREEN` |
| GitHub repository, branch, and merge constraints | `NONE` / `REPO: owner/name; BRANCH: branch; MERGE: ALLOWED\|PROHIBITED` |
| AWS boundary | `NONE` / `DOCS_ONLY` / `READ_ONLY` / `MUTATE_LISTED_RESOURCES` |
| AWS account | TODO / `NOT_APPLICABLE — <reason>` |
| AWS role or profile | TODO / `NOT_APPLICABLE — <reason>` |
| AWS Region | TODO / `NOT_APPLICABLE — <reason>` |
| AWS environment | `ENVIRONMENT: <exact name>; CLASS: NON_PRODUCTION\|PRODUCTION` / `NOT_APPLICABLE — <reason>` |
| AWS stack or application | TODO / `NOT_APPLICABLE — <reason>` |
| AWS resource allowlist | TODO / `NOT_APPLICABLE — <reason>` |
| AWS allowed operations | TODO / `NOT_APPLICABLE — <reason>` |
| AWS cost ceiling | TODO (finite positive ISO-currency amount such as `USD: 20.00`) / `NOT_APPLICABLE — <reason>` |
| AWS prohibited operations | TODO / `NOT_APPLICABLE — <reason>` |
| AWS artifact authorization and provenance | `EXACT_DIGEST: sha256:<64 lowercase hex>` / `DERIVED_FROM_AUTHORIZED_SOURCE: SHA-256 from baseline <full authorized commit>; <deterministic rule>` / `NOT_APPLICABLE — <reason>` |
| AWS rollback boundary | TODO / `NOT_APPLICABLE — <reason>` |
| AWS authorization validity | `Expires at <ISO 8601 with timezone>; earlier completion: <exact condition>` / `NOT_APPLICABLE — <reason>` |
| Rollback, recovery, and teardown boundary | TODO |
| Mandatory stop conditions | TODO |
| Authorization expiry or completion condition | `Expires at <ISO 8601 with timezone>; earlier completion: <exact condition>` |

The Engine owns the envelope grammar, digest, compatibility, and staleness rules.
This table is the complete bounded local-construction authority presented at Gate B.

</details>

## 29. Gate B owner authorization record

| Field | Owner-provided value |
|---|---|
| Approver | TODO |
| Owner decision | `PENDING` / `CHANGES_REQUESTED` / `APPROVED` / `STALE` |
| Authorized requirements revision | TODO |
| Authorized design revision | TODO |
| Authorized construction authorization ID | TODO |
| Authorized construction envelope SHA-256 | TODO (`sha256:` plus 64 lowercase hex characters) |
| Authorization provided at | TODO (ISO 8601 with timezone) |
| Authorization source | TODO (message, issue, meeting record, or commit link) |
| Verbatim owner receipt | `RECORDED_BELOW` / `TODO` |
| Derived Gate B state | `BLOCKED` / `PENDING_OWNER_APPROVAL` / `APPROVED_FOR_CONSTRUCTION` / `STALE` |

For approval, the owner receipt must use this human-readable form with actual
values substituted:

<!-- bootstrap:gate-b-receipt:start -->
```text
APPROVE PRD AND CONSTRUCTION GATE B
Requirements revision: <REQ-nnnn>
Design revision: <DES-nnnn>
Construction authorization: <AUTH-nnnn>
Construction envelope SHA-256: sha256:<64-lowercase-hex>
Use the proposed construction envelope above.
Approver: <name/handle>
```
<!-- bootstrap:gate-b-receipt:end -->


# Contract Appendices

Exact records below remain machine-validated and auditable. They do not add an owner gate or authority.

<details>
<summary>Exact Gate B record-maintenance and validation rules</summary>

## Exact record maintenance

Project facts and owner decisions remain in this PRD. Phase procedures, receipt syntax, and Engine schemas remain in their designated Fastlane authorities; `docs/project/AGENTS.md` narrows safe edits here.
## 30. Gate B validation and invalidation rules

The Engine validates current Gate A, complete design and Harness coverage,
matching REQ/DES/AUTH identities and digests, the exact owner receipt, bounded
construction, and deterministic staleness. Changes follow the existing Gate A
or Gate B invalidation boundary; evidence-only progress inside the envelope does
not create new authority.

</details>
