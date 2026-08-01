# AWS Codex Fastlane Workflow

Fastlane turns an app idea or bounded change into owner-approved requirements, one AWS-informed technical design, and a tested local build inside an explicit boundary. Codex is the sole coordinator/writer; the Fastlane Engine routes and validates; AWS Core supplies current AWS guidance; the owner decides and authorizes.

## Start

Send `init template`. A fresh template checks signed-in Codex, Git, Python 3.11+, sandbox support, `uvx`, and current official AWS Core without inspecting credentials or accessing an AWS account. Missing items appear in one consolidated checklist. Ready setup asks once for project name, preferred Region, and development budget; an initialized project resumes without repeating setup.

Repository state and owner work context are separate. After setup, Fastlane asks exactly one unanswered app question per owner turn: starting point; users and current problem; first useful end-to-end result; first-release boundary; observable success; data; sensitivity/access; initial audience; material geography; then only coverage-required reliability, recovery, legal, or operational decisions. It skips facts already supplied.

A decision uses plain A/B/C options, practical consequences, one justified recommendation when possible, its main tradeoff, and a short copyable reply. A factual question uses bounded free text. Rendering the current card ends the turn. Only a new inbound owner message can resolve the exact current card ID, revision, and canonical digest. A recommendation, example, stale reply, assistant text, or absent reply never confirms a choice.

The deterministic sequence is owner response → parse → normalized canonical write → Engine revalidation → Answer Confirmation → next question. The confirmation states what was recorded, its practical project effect, and `Change <plain field> to <new value>.` It is bound to the new `OWNER-MSG-*` for that turn and is not replayed on resume.

`Accept all recommendations.` requires no visible reply token and applies only to the exact current eligible decision with a complete recommendation and no missing detail. Matching `R-*` input remains hidden 1.0.x compatibility for that exact card. Gate corrections are `Change the requirements: <correction>.` and `Change the design: <correction>.`; neither is approval.

## Lifecycle

| Phase | Outcome | Owner decision |
|---|---|---|
| BOOT-00 | Repository initialized or safely resumed | Fresh setup only |
| INTAKE-10 / REQ-10 | Owner-grounded requirements and success criteria | Answer one current question |
| Gate A / INTAKE-20 | Exact requirements revision reviewed | Approve requirements for design |
| DESIGN-10 | Complete technical plan, AWS evidence, diagrams, and construction envelope | None unless a material decision remains |
| Gate B / DESIGN-20 | Exact design and construction boundary reviewed | Approve construction |
| TASK-10 / BUILD | Dependency-aware local construction and evidence | No task-by-task approval |
| RELEASE-10 | Release evidence reconciled | Only when its contract requires it |
| AWS-10 | Read-only deployment preflight | Authorize the exact read-only account, identity, scope, operations, and expiry |
| AWS-20 | Authorized deployment mutation | Current fast-dev envelope or separate explicit-gate receipt |
| AWS-30 | Read-only deployment reconciliation | Exact read scope when no current reusable receipt covers it |
| AWS-40 | Residual review and teardown readiness | Choose a residual disposition when required; authorize reads when needed |
| AWS-50 | Authorized teardown mutation | Separate exact teardown authorization |

Gate A — approve requirements → Gate B — approve design and construction → Codex builds locally inside that boundary. Gate A continues into Design in the same run. Gate B continues into task generation in the same run. BUILD never deploys.

After Gate B, Codex builds locally. For AWS preflight, deployment verification, or teardown preparation, ask Codex to use `$operate-fastlane-aws`. Every AWS mutation still requires its exact separate authorization.

BUG-10, SYNC-10, and explanation are request-scoped adjuncts, not routes or gates. They preserve the Engine route/action, perform only bounded work, rerun the Engine, and restore the pending action.

## Owner Decision Briefs

The Engine derives an `owner_decision_brief` from the one canonical PRD. The presenter renders it; it is never another editable ledger.

- Gate A covers outcome, users, first-release journey, scope/non-goals, success, data/access, deletion/recovery, Region/cost, assumptions, risks, brownfield preservation, change lineage, authorization effect, next step, and the exact receipt.
- Gate B opens with a one-minute executive decision, then groups consequential decisions by application/runtime, identity, data, messaging, edge/networking, observability, deployment/recovery, and validation/construction. Each claim has an exact maturity, basis/evidence IDs, and repository-relative source locator.
- Claim maturity distinguishes owner confirmation, repository observation, source verification, local observation, AWS read observation, deployment/recovery observation, planning, absence of observation, and absence of authorization.
- Gate A and Gate B receipts remain the only approvals and appear last. A valid receipt continues automatically; a correction never approves.

Source locators use repository-relative paths, one-based inclusive lines, and SHA-256 of LF-normalized UTF-8 section bytes ending in one LF. They never expose a home path, credential, remote with credentials, or unverified permalink.

## Canonical records and diagrams

Requirements contract 1.4 records revision lineage and the assumption lifecycle. Unchanged approved schema 1.3 is grandfathered until a requirements-controlled change; the older approved 1.2 bridge remains exact and read-only.

Design contract 6 adds the Project diagram contract. New designs require `SYSTEM_CONTEXT` and `PRIMARY_OUTCOME`; data, recovery, and migration views are conditional on canonical records. Fresh templates show honest `NOT_YET_CREATED` slots, never fake application architecture. Canonical IDs identify Mermaid nodes and plain labels explain them. Semantic relationships affect the design digest; render-only drift blocks the brief until Codex regenerates it. Diagrams describe planned design and never prove code, deployment, evidence, or authority. Unchanged approved schema 4 or 5 designs remain valid only for their exact design/envelope until a controlled design change.

The project record starts at [docs/project/README.md](project/README.md): PRD owns requirements/design/gates; TASKS owns execution state; VERIFY owns evidence; RUNBOOK owns operations. Human summaries come first and exact records remain in appendices. There is no separate human PRD.

## Internal delivery rules

These are internal conditional techniques, not lifecycle stages or approval gates. They stay out of ordinary owner conversation.

- Normative requirements use the Fastlane EARS Contract with measurable/Gherkin acceptance. New builds receive complete architecture comparison; bounded changes use AMEND or evidence-backed PRESERVE. The first NEW_BUILD task is a walking-skeleton/Thin Vertical Slice tied to the approved `WAVE-*`.
- Baseline security, testing, observability, and error handling always apply. STRIDE, LINDDUN, OWASP Top 10, ATAM, ADR, and formal inspection deepen work only for material exposure, privacy, hard-to-reverse decisions, or high/critical risk. They are not another lifecycle; procedural technique selection never claims deterministic proof.
- Gate B records one risk-derived Harness Profile. Applicable checks are `REQUIRED` with exact commands, conditional checks name triggers, and inapplicable checks give concrete technology/risk reasons. No universal scanner is imposed.
- Semantic Anchors are optional design vocabulary, not a Fastlane package, runtime dependency, owner workflow, authority, methodology, or source of truth.
- Project diagrams are validated presentation of canonical records. They do not replace traceability, tests, or evidence.

## AWS Core and authority

Fastlane requires the current official
`aws-core@agent-toolkit-for-aws` from `aws/agent-toolkit-for-aws`. Fresh setup runs one credential-free `search_documentation` for `AWS skills`, then matching `retrieve_skill`. Material Define, Design, and AWS-10 questions run their own current discovery chains. Installed metadata, cache, generic connectors, and model memory are not proof of use.

Codex selects and coordinates the architecture. AWS Core supplies current AWS knowledge, decision guidance, procedures, and execution tools; it cannot approve or authorize. Fastlane records attributable `AWS-DISC-*`/`AWS-EV-*` evidence but persists no raw skill content or transcripts.

An AWS lane is planned access, not authority. Gate B's `AWS allowed operations` is the maximum union across AWS-10, AWS-20, AWS-30, AWS-40, and AWS-50. Each phase may use only its current intersection with exact evidence and action authority. An explicit-gate maximum grants no mutation by itself. IAM remains downstream enforcement.

`operate-fastlane-aws` owns execution procedure. Deployment flows AWS-10 → AWS-20 → AWS-30 and only AWS-20 may mutate. Teardown flows AWS-40 → AWS-50 → AWS-40 and only AWS-50 may mutate. Read, deployment, and teardown receipts are separate.

AWS-30 stores `SOURCE: <stable owner-message source>; AUTHORIZED_AT: <ISO 8601 with timezone>; RESOURCES: <exact canonical list>; OPERATIONS: <exact canonical list>`. `AUTHORIZED_AT` comes from the matching Read-only preflight row in Action authorization provenance. Current exact-scope evidence matches resources/operations; other current reads may observe a subset. STALE never claims fresh reads. STARTED is not proof of a call; terminal evidence and independent read reconciliation determine what occurred.

For residuals, follow `aws_residual_disposition` while it is PENDING. One set-level choice covers the complete current residual set: RETAIN, INVESTIGATE, or REMOVE. Every choice after `RESIDUALS_REMAIN` must be strictly newer. After READY, RETAIN and INVESTIGATE must be strictly newer, while owner-provenanced TEARDOWN may carry forward as REMOVE. REMOVE may present an exact teardown receipt only after current readiness; lifecycle intent itself never authorizes account access.

## Focused context and continuation

The Engine resolves exact source slices. `maximum_initial_bytes` and `maximum_initial_source_bytes` both mean at most 12,000 canonical repository source bytes, not tokens or total model context. `resolved_initial_slices` load first; `resolved_on_demand_slices` are not an implicit initial load. Each slice reports path, selector, one-based inclusive lines, digest, bytes, IDs, and reason.

Never silently truncate a row or blocking record. Lower-priority material moves on demand. One oversized required atomic record is included once and reported honestly without creating owner work. Invalid/ambiguous sources fail closed. Packets are ephemeral and untracked; runtime AWS skill content is external context and is not counted as repository bytes.

A ready Quick MVP with a complete brief needs at most one clarification round before Gate A. Setup and completed decisions never repeat. Every pause shows one next action. Safe Codex-owned corrections continue within write and attempt boundaries; owner or human actions appear only at genuine semantic, approval, authorization, protected-boundary, or safety boundaries.

## Framework maintenance

Framework work uses `maintain-fastlane`, never the adopter lifecycle. `AUDIT` and `PLAN` are read-only. `IMPLEMENT` requires an exact baseline, outcome, non-goals, allowlist, acceptance criteria, and change budget. Missing implementation scope stops before edits. `PUBLISH` is separately authorized; publication never follows from edit authority. Unrelated findings remain report-only.

The live `fast-lane` customer branch uses short-lived branches and pull requests targeting only that customer branch. Required checks are `safety-tests (3.11)`, `safety-tests (3.12)`, `safety-tests (3.13)`, `windows-smoke`, and `macos-setup-smoke`; the branch must be current. Force pushes and deletion are blocked. A direct push to `fast-lane` requires explicit emergency publication authority. Protected `fast-lane-maint` preserves 1.0.5; legacy `Legacy` is not a customer publication target. Branch-rule changes remain a separate repository-setting action.

Use the read-only maintenance preflight before IMPLEMENT/PUBLISH and deterministic package comparison against the exact base commit. A source change requires a newer package version and current manifest; neither tool publishes.

## Optional hooks, qualification, and resume

Fastlane works with hooks disabled. The reviewed optional hook pack may deny clearly out-of-bound requests but never creates approval, authority, or canonical state. The Engine must remain correct without it.

Before claiming a real AWS execution lane as field-qualified, Codex selects the smallest disposable scenario using current AWS Core guidance. The owner authorizes; IAM enforces; observed evidence proves. AWS Core does not choose the product architecture or grant authority. Field qualification adds no scorer, lifecycle stage, gate, or routine customer action.

On resume, the Engine selects the current route and one next action. Initialized projects skip setup. A missing current AWS capability pauses only the affected material AWS step. Schema-5 model role plays remain opt-in, external-evidence checks for the Fastlane 1.1 customer journeys; they are never ordinary CI or independent release-readiness proof.

## Agent reference

Global invariants live in `AGENTS.md`; phase procedures in Fastlane references; exact receipts in the prompt registry; deterministic schemas/routing in the Engine and tests; operations in `operate-fastlane-aws`; project truth in `docs/project/`.
