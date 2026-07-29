# Define phase

Use for BOOT-00, INTAKE-10, REQ-10, and Gate A.

- Before a fresh-template welcome or write, require the read-only prerequisite
  result `PREREQUISITES_READY`. Render all missing dependencies as one owner
  checklist. Never install or persist client state.
- After prerequisites pass, ask project name, preferred Region, and optional
  budget exactly once, then initialize dry-run-first.
- Initialized projects skip prerequisites and resume the derived stage. Never
  repeat completed setup questions.
- Keep repository mode separate from owner work context. A greenfield or empty
  repository does not prove a new application. Ground `INTAKE-*` rows in the
  owner's users, problem, observable outcome, first-release boundary, success
  measure, and material data/operating boundaries before requirements are ready.
- Store one current `INTAKE-CARD-*` in PRD intake provenance. Decisions use
  uppercase A/B/C, at most three questions, a practical effect and tradeoff,
  any required supporting detail, and one exact reply. Facts use short free
  text rather than invented choices.
- Do not invent a universal default. Recommend an option only when current
  owner or repository evidence justifies it. Otherwise render exactly
  `No recommendation—choose the option that matches your situation.` and use
  the neutral copyable form `1: <choose A, B, or C>` for that decision.
- A recommendation, copyable example, prior message, ambiguous shorthand, or
  absent reply is never owner confirmation. Resolve only the current card from
  a new owner response. Before any PRD or derived-state write, run the
  deterministic intake-response parser against the exact current card ID,
  revision, digest, and a new `OWNER-MSG-*` ID. A rejected parse causes zero
  writes: use its owner-safe status, preserve the entire card, and give the
  exact reply-specific correction without echoing secret-like input. A
  successful partial parse updates only returned reply keys and leaves the
  remaining questions pending on the same card. Then rerun the Engine. The card
  is the final action when its turn boundary is set.
- Unapproved legacy intake never gains synthetic owner provenance. Retain prior
  values only as unconfirmed context, reopen the affected facts, and present the
  smallest current card. Grandfather only an unchanged approved Gate A.
- The `Accept all recommendations.` payload applies only after the current reply
  token and when every question is a decision with a complete recommended option
  that needs no supporting detail. Never apply it to a factual, partially
  recommended, stale-token, or changed card.
- Normalize lowercase decision letters to uppercase. For the initial work
  context decision, project `A` to `NEW_APPLICATION`, `B` to
  `EXISTING_APPLICATION_CHANGE`, and `C` to `REPAIR_OR_MIGRATION`. Record each
  parsed answer in the owner-response register, its card row, and every cited
  foundation row using the same card-bound provenance. Multiple facts derived
  from one question must cite the same parsed record. This provenance proves
  deterministic interpretation; it is not identity authentication.
- Ask no more than three related, plain-language owner decisions per response.
- Lead with the real-world consequence. Keep `RTO`, `RPO`, `p95`, concurrency,
  metadata, and methodology labels in internal records unless the owner used
  the term or explicitly asks for technical detail. Translate them using the
  Owner responses reference, mark one recommendation only when justified with
  its main tradeoff, and provide a short copyable reply. Permit the current
  token-bound `R-*; Accept all recommendations.` alternative only when every
  presented question is a decision with a complete recommendation and no
  required supporting detail.
- Separate owner facts, repository facts, recommendations, proposed
  assumptions, and unresolved decisions.
- Give requirements and assumptions stable IDs and observable acceptance
  criteria. Preserve brownfield behavior and protected user work.
- Translate only normative requirement rows into the Fastlane EARS Contract with one canonical form and
  one `GHERKIN` or `MEASURABLE` acceptance form. Keep goals, stories, facts,
  assumptions, decisions, tasks, tests, receipts, and evidence outside the contract.
  Do not expose methodology labels unless the owner asks for an explanation.
- Add `QAS-*` rows only for material performance, availability, reliability,
  recovery, scalability, security-response, or operational-response concerns;
  otherwise record `NOT_APPLICABLE — <concrete reason>`.
- Complete the schema 1.3 actor, journey, business-rule, acceptance-ID, and
  requirement-coverage records before Gate A is ready. Require richer use-case
  guarantees only for high/critical risk or a declared material journey
  trigger. Never invent missing owner facts to complete those records.
- Derive one internal Adaptive Coverage Plan before Gate A. Infer the work kind
  and `SELECT`/`AMEND`/`PRESERVE` disposition without adding an owner question.
  Every omission needs a current requirement or repository basis; uncertain
  impact uses full coverage. Quick MVP changes depth, never safety.
- Use STRIDE only when material security trust boundaries require systematic
  analysis. Use LINDDUN only when materially privacy-sensitive data requires
  systematic analysis. Record resulting requirements, controls, tests, and
  evidence in existing Fastlane authorities; neither method adds a gate.
- Default cost posture to `MINIMIZE_TOTAL_COST; HARD_CAP_NOT_STATED`; preserve
  an owner cap exactly.
- Quick MVP uses no challenger by default. Use the requirements challenger only
  for ambiguity, contradictions, sensitive data, identity, payments,
  migrations, shared interfaces, high risk, or explicit owner request, and
  only after the complete requirement draft exists with no open owner decision.
  Attempt it once per requirements revision for at most 60 seconds. On failure,
  timeout, or unavailability, record that independent review was unavailable in
  the existing recommendation rationale, run the checklist as coordinator, and
  continue without exposing reviewer orchestration or adding an owner action.
- Classify REQ-10 AWS Core materiality as `REQUIRED`, `OPTIONAL`, or
  `NOT_MATERIAL`. Use `REQUIRED` when Gate A depends on a current AWS fact about
  Region/service feasibility, identity/authorization, sensitive data/uploads,
  public exposure, encryption, deletion/recovery, quotas, availability, or
  material cost. The coordinator must search current documentation, select a
  returned identifier, and retrieve that exact identifier in one linked chain
  bound to the current REQ and affected requirements. This is documentation-only
  evidence: inspect no credentials, access no account, and select no final
  architecture before Gate A.
- The coordinator writes analysis and the readiness card; only the owner may
  approve the exact Gate A receipt.
