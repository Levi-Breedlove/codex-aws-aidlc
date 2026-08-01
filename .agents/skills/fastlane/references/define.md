# Define phase

Use for BOOT-00, INTAKE-10, REQ-10, and Gate A.

- Before a fresh-template welcome or write, require read-only
  `PREREQUISITES_READY`. Render all missing dependencies in one owner checklist;
  never install or persist client state.
- Then ask project name, preferred Region, and optional budget once; initialize
  dry-run-first using the exact ephemeral ready report on stdin for both
  bootstrap calls. Never persist the report. Initialized projects skip
  prerequisites and resume without repeated setup.
- Keep repository mode separate from owner work context. A greenfield or empty
  repository does not prove a new application. Ground `INTAKE-*` rows in the
  owner's users, problem, observable outcome, first-release boundary, success
  measure, data types, data sensitivity, release audience, and operating
  geography before requirements are ready. Record clear facts from the owner's
  brief first and ask only for missing or ambiguous material facts.
- Frame missing facts as a human consultation, not field labels. Ask in this
  order when still unanswered: what the owner is starting with; who it is for;
  what is hardest for them today; what useful result the first version should
  provide; what must be included now and what can wait; what visible result
  would prove the first trial helped; what information people will enter,
  upload, view, or generate; whether it can reveal identity, health, money,
  location, credentials, or another sensitive detail; who may use the first
  release; and where users will be or data must stay. Use concrete examples
  sparingly, accept `recommend one` or `not sure`, and ask only the next missing
  question. A complete owner brief may ground several rows without repetition.
- Store one current `INTAKE-CARD-*` in PRD intake provenance. Decisions use
  uppercase A/B/C, exactly one question, an effect, tradeoff, required detail,
  and exact reply. Facts use short free text, not invented choices.
- Recommend only with current owner or repository evidence. Otherwise render
  exactly
  `No recommendation—choose the option that matches your situation.` and use
  the neutral copyable form `1: <choose A, B, or C>` for that decision.
- Recommendations, examples, prior messages, ambiguous shorthand, and absent
  replies never confirm. Resolve only the current card from a new owner
  response. Before a PRD or derived-state write, run the deterministic parser
  against its exact ID, revision, digest, and a new `OWNER-MSG-*` ID. Rejection
  writes nothing: use its owner-safe status, preserve the card, and give the
  exact reply correction without echoing secret-like input. A valid response
  resolves only that question. Rerun the
  Engine; render `owner_answer_confirmation` only with that turn's matching
  `OWNER-MSG-*` identity before the next question. Never replay it on resume.
  When set, the card's turn boundary makes it the final action.
- Never synthesize owner provenance for unapproved legacy intake. Keep prior
  values as unconfirmed context, reopen affected facts, and present the smallest
  current card. Grandfather only an unchanged approved Gate A.
- `Accept all recommendations.` applies only to the exact current card when
  the current question is a decision with a complete recommendation and no
  supporting detail. Never apply it to factual, stale, or changed cards.
- Normalize lowercase decision letters to uppercase. For the initial work
  context decision, project `A` to `NEW_APPLICATION`, `B` to
  `EXISTING_APPLICATION_CHANGE`, and `C` to `REPAIR_OR_MIGRATION`. Record each
  answer in the owner-response register, card row, and cited foundation rows
  with the same card-bound provenance. Facts from one question cite the same
  parsed record. This proves deterministic interpretation, not identity.
- After the three initial settings, ask exactly one plain-language intake question per owner turn.
- Lead with the real-world consequence. Keep `RTO`, `RPO`, `p95`, concurrency,
  metadata, and methodology labels internal unless the owner used them or asks
  for technical detail. Translate via the Owner responses reference; give one
  justified recommendation with its main tradeoff and a short copyable reply.
  Permit plain `Accept all recommendations.` only when the current question
  is a decision with a complete recommendation and no supporting detail.
- Separate owner facts, repository facts, recommendations, proposed
  assumptions, and unresolved decisions.
- Give requirements and assumptions stable IDs and observable acceptance
  criteria. Preserve brownfield behavior and protected user work.
- Translate only normative rows into the Fastlane EARS Contract: one canonical
  form and one `GHERKIN` or `MEASURABLE` acceptance form. Keep goals, stories,
  facts, assumptions, decisions, tasks, tests, receipts, and evidence outside;
  expose methodology labels only when the owner asks.
- Add `QAS-*` rows only for material performance, availability, reliability,
  recovery, scalability, security-response, or operational-response concerns;
  otherwise record `NOT_APPLICABLE — <concrete reason>`.
- Complete the schema 1.3 actor, journey, business-rule, acceptance-ID, and
  requirement-coverage records before Gate A is ready. Require richer use-case
  guarantees only for high/critical risk or a declared material journey
  trigger. Never invent missing owner facts to complete those records.
- Make traceability bidirectional: every authoritative first-release
  requirement appears exactly once in coverage, and every declared `ACT-*` and
  `JOURNEY-*` participates in at least one of those rows. For each requirement,
  `Acceptance/test IDs` is exactly its canonical `AC-*` followed only by
  `TEST-*`, `PROP-*`, or `EV-*` IDs explicitly named in that same requirement's
  acceptance criterion. Never add a convenient but undeclared validation ID.
- Rich-use-case policy is journey-specific. At low or moderate risk, every
  journey declaring a material rich-use-case trigger has a rich use case bound
  to that journey. At high or critical risk, every declared journey has one.
  The typed journey row is authoritative; applicability prose cannot move the
  obligation to an easier journey.
- Derive one internal Adaptive Coverage Plan before Gate A. Infer the work kind
  and `SELECT`/`AMEND`/`PRESERVE` disposition without adding an owner question.
  This is a one-way mapping: when confirmed owner work context is
  `NEW_APPLICATION`, Work kind must be `NEW_BUILD`; `NEW_BUILD` never infers or
  replaces owner work context. Omissions need current requirement or repository
  basis; uncertain impact uses full coverage. Quick MVP changes depth, not safety.
- Use STRIDE only when material security trust boundaries require systematic
  analysis. Use LINDDUN only when materially privacy-sensitive data requires it.
  Use an OWASP Top 10 review when a material web, API, or application attack
  surface applies. Record results in existing requirement, control, test,
  Harness, and evidence authorities; none of these methods adds a gate.
  Selecting and applying STRIDE, LINDDUN, or OWASP Top 10 is procedural
  coordinator review;
  deterministic validation covers the resulting bound records, not proof that
  the review method itself occurred.
- Default cost posture to `MINIMIZE_TOTAL_COST; HARD_CAP_NOT_STATED`; preserve
  an owner cap exactly.
- Quick MVP has no challenger by default. When ambiguity, contradiction,
  sensitive data, identity, payments, migration, a shared interface, material
  risk, or an owner request justifies review, use one read-only attempt per exact
  requirements revision after
  the complete draft has no open owner decision. Allow 5 minutes for Quick MVP
  or Standard requirements review and 30 minutes for high-risk or explicit
  deep review. Check progress at least every 60 seconds and finish early. If it
  fails, times out, or is unavailable, record that in the existing
  recommendation rationale, run the coordinator checklist, and continue
  without exposing reviewer orchestration or adding an owner action.
- Classify REQ-10 AWS Core materiality as `REQUIRED`, `OPTIONAL`, or
  `NOT_MATERIAL`. Use `REQUIRED` when Gate A depends on a current AWS fact about
  Region/service feasibility, identity/authorization, sensitive data/uploads,
  public exposure, encryption, deletion/recovery, quotas, availability, or
  material cost. The coordinator searches current documentation and retrieves
  an exact returned identifier in one chain bound to the current REQ and
  affected requirements. This is documentation-only: inspect no credentials,
  access no account, and select no final architecture before Gate A.
- Keep AWS Core remediation ownership exact. A genuinely unavailable official
  capability is owner setup. Missing, stale, or safely repairable generated
  discovery/evidence while the capability is available is Codex work; refresh
  it and revalidate without asking the owner to reinstall. Unexplained
  structural drift or an unsafe evidence conflict requires human review.
- The coordinator writes analysis and the readiness card; only the owner may
  approve the exact Gate A receipt.
