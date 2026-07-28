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
- A recommendation, copyable example, prior message, ambiguous shorthand, or
  absent reply is never owner confirmation. Resolve only the current card from
  a new owner response, record normalized `OWNER_RESPONSE` provenance, then
  rerun the Engine. The card is the final action when its turn boundary is set.
- `Accept all recommendations.` applies only to the current card and only when
  every question is a decision with a complete recommended option.
- Ask no more than three related, plain-language owner decisions per response.
- Lead with the real-world consequence. Keep `RTO`, `RPO`, `p95`, concurrency,
  metadata, and methodology labels in internal records unless the owner used
  the term or explicitly asks for technical detail. Translate them using the
  Owner responses reference, mark one recommendation with its main tradeoff,
  and provide a short copyable reply. Permit `Accept all recommendations.`
  when every presented default is complete and safe to accept together.
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
- Use AWS Core only when a current AWS fact materially affects feasibility.
- The coordinator writes analysis and the readiness card; only the owner may
  approve the exact Gate A receipt.
