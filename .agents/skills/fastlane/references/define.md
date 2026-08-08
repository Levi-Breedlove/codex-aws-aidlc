# Define phase

Use for BOOT-00, INTAKE-10, REQ-10, and Gate A. The Engine owns routing and validation; this reference owns the phase procedure.

## Setup and intake

- A fresh template requires ephemeral `PREREQUISITES_READY` evidence before any welcome or write. Show every missing dependency in one consolidated checklist; never install dependencies or persist client, credential, plugin, trust, path, or readiness state. Initialized projects resume without setup.
- Ask project name, preferred Region, and optional budget once, then initialize dry-run-first with the exact ephemeral report supplied on stdin.
- Repository mode (`GREENFIELD` or `BROWNFIELD`) never determines owner work context. Ground `INTAKE-*` facts in the owner's brief before asking anything. An empty repository does not prove a new application.
- Ask the starting-point decision first because repository contents cannot prove
  owner intent. After it is confirmed, follow the Engine's
  `next_question_guidance`: tailor one natural consultation question to a new
  application, an existing-application change, or a repair or migration. One
  coherent fact question may collect its closely related target facts. Then
  cover only the remaining first-release boundary, visible success, data and
  sensitivity, audience, geography, and coverage-required reliability,
  recovery, legal, or operational decisions. Skip anything already stated or
  observed.
- Project mode, delivery profile, effective risk, and AWS lane are internal
  technical classifications, not owner choices. Follow the Engine's
  `project_configuration` projection after the intake foundation is complete:
  use its derived mode, keep the current Define lane `documentation-only`,
  classify risk and profile from the cited confirmed facts, synchronize the PRD
  and `bootstrap.yaml`, and rerun the Engine. A conflict is a Codex correction
  before Gate A; never fabricate owner provenance for it.
- Store one current `INTAKE-CARD-*` with exactly one question. Decisions use uppercase A/B/C and A is recommended only when current evidence justifies it; facts use bounded free text. Explain the real-world consequence before technical terminology, show the main tradeoff, require supporting detail when needed, and provide one exact short reply.
- With no sound recommendation, say `No recommendation—choose the option that matches your situation.` Recommendations, examples, prior messages, ambiguous shorthand, assistant text, and an absent reply never confirm a choice.
- Resolve only the exact current card from a new inbound owner message. Run the deterministic parser against its ID, revision, presented digest, and new `OWNER-MSG-*` identity before writing. Invalid or secret-like input changes nothing and receives an owner-safe correction. A valid reply writes normalized `OWNER_RESPONSE` provenance, reruns the Engine, and renders `owner_answer_confirmation` only for that new turn before the next question. An owner-input card ends the assistant turn.
- `Accept all recommendations.` applies only to the current decision when its recommendation is complete and needs no detail. It never resolves a factual, stale, changed, or multi-question legacy card. Hidden matching `R-*` input remains compatibility-only and is never displayed.
- Migrate an unapproved multi-question 1.0.x card by reissuing only its first unresolved question with a new revision and digest. Keep remaining facts open. Never synthesize owner provenance. Preserve an unchanged approved Gate A until a requirements-controlled change.
- After setup, use one owner decision per turn. A complete owner brief may ground several facts without repetition. Keep acronyms such as RTO, RPO, p95, concurrency, metadata, EARS, QAS, and Harness internal unless the owner used them or asks for technical detail.

## Requirements and Gate A

- Keep owner facts, repository observations, Codex recommendations, assumptions, and open decisions distinct. Owner-controlled semantics are never inferred.
- Requirements contract 1.4 adds the current requirements change lineage and assumption lifecycle. Each change row binds prior/current revision, trigger, added/changed/removed/preserved IDs, stale reason, and required revalidation. Assumptions use `PROPOSED`, `ACCEPTED`, `VALIDATED`, `INVALIDATED`, or `SUPERSEDED`. Existing unchanged approved schema 1.3 is grandfathered; new, unapproved, or changed requirements use 1.4.
- Give each normative requirement one stable ID, one observable obligation in the Fastlane EARS Contract, one canonical `AC-*`, and `GHERKIN` or `MEASURABLE` acceptance. Goals, stories, facts, assumptions, decisions, tasks, tests, receipts, and evidence are not EARS rows.
- Build actors, journeys, conditional rich use cases, business rules, and exact requirement coverage from owner-grounded facts. Actor kinds are `PRIMARY_USER`, `SECONDARY_USER`, `OPERATOR`, or `EXTERNAL_SYSTEM`. Trace every first-release requirement exactly once and bind every `ACT-*` and `JOURNEY-*`. Never invent an owner fact to complete a record.
- Rich-use-case triggers are `DISTINCT_PERMISSIONED_ACTORS`, `CONFIDENTIAL_OR_REGULATED_MUTATION`, `MONEY_OR_ENTITLEMENT`, `IRREVERSIBLE_ACTION`, `MIGRATION_OR_CUTOVER`, `ASYNCHRONOUS_WORK`, `PARTIAL_FAILURE`, or `NONE`. At low/moderate risk, each triggered journey owns a rich use case; at high/critical risk, every journey does. Keep applicability journey-specific.
- Apply the Engine's requirements migration exactly: unchanged approved legacy contracts retain their grandfathered digest; unapproved legacy records migrate before Gate A; a requirements-controlled change uses 1.4 and invalidates both gates. Do not rewrite owner facts merely to modernize record shape.
- Add `QAS-*` only for material performance, availability, reliability, recovery, scalability, security-response, or operational-response concerns; otherwise record `NOT_APPLICABLE — <concrete reason>`.
- Derive the Adaptive Coverage Plan without another question. Confirmed `NEW_APPLICATION` requires `NEW_BUILD`, but never infer owner context from repository state or work kind. `SELECT`, `AMEND`, and `PRESERVE` change design coverage, not safeguards. Unsupported omissions or uncertain impact use full coverage; Quick MVP changes depth, never safety.
- Use STRIDE only when material trust boundaries warrant it, LINDDUN only when materially privacy-sensitive data warrants it, and OWASP Top 10 only for a material application attack surface. Selecting and applying STRIDE, LINDDUN, or OWASP Top 10 is procedural coordinator review; record conclusions in existing requirements, controls, tests, Harness, and evidence, never a new stage or gate.
- Default cost posture to `MINIMIZE_TOTAL_COST; HARD_CAP_NOT_STATED`; preserve an owner cap exactly. Gate A remains approval of requirements only and never authorizes AWS access or spend.

## Review and AWS evidence

- Run a read-only requirements challenger only after the complete draft has no open owner decision and only when ambiguity, contradiction, sensitive data, identity, payments, migration, shared interfaces, material risk, explicit deep review, or evaluation mode justifies it. Quick MVP uses none by default; a justified Quick MVP or Standard review gets 5 minutes, and high-risk/deep review gets 30 minutes. Attempt once per exact requirements revision, check progress at least every 60 seconds, and finish early. If unavailable or timed out, record that fact, perform the coordinator checklist, and continue without exposing orchestration or making reviewer failure owner work.
- Classify REQ-10 AWS materiality as `REQUIRED`, `OPTIONAL`, or `NOT_MATERIAL`. When Gate A depends on a current AWS fact—service/Region feasibility, identity, sensitive data or uploads, public exposure, encryption, deletion/recovery, quotas, availability, or material cost—use `search_documentation`, then matching `retrieve_skill`, and bind one current `AWS-DISC-*` chain to the current REQ and affected IDs. Keep it credential-free, account-free, documentation-only, and architecture-neutral.
- Capability unavailability is owner setup. Missing or stale generated discovery while capability is available is Codex work. Unsafe or unexplained evidence drift requires human review.
- The coordinator writes the analysis and readiness card. Only the owner can approve the exact Gate A receipt.
- The Gate A Owner Brief is the complete human review of the Product Agreement. It includes the outcome, users, first-release journey, scope and non-goals, data and access boundaries, deletion and recovery expectations, Region and cost, measurable acceptance, every owner decision and source, claim maturity, corrections, unauthorized work, and what follows approval.
- Resolve every Gate A source link from the current canonical PRD headings. Put those links before the exact receipt; after receipt-only approval, the first automatic Design update links back to Gate A and forward to the Technical Plan.
