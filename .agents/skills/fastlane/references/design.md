# Design phase

Use for DESIGN-10 and Gate B.

- Complete the whole-system architecture, security, data, failure, recovery,
  operations, cost, deployment, rollback, teardown, and verification design.
- For each material AWS question, identify its current basis IDs, use
  `search_documentation` to discover relevant runtime skills, review returned
  descriptions, select the smallest covering set, and `retrieve_skill` with
  those exact returned identifiers. Follow the retrieved procedures and load
  references only as needed. Record linked `AWS-DISC-*` rows, conclusions,
  IDs, official sources, times, and bindings—not raw instructions or tool
  transcripts. Generic connectors, memory, or installed-skill metadata and
  challenger prose cannot replace those calls.
- Installing the plugin or selecting `@AWS-Core` proves availability only.
  Attribute AWS Core use only after the current linked search-then-retrieve
  chain validates; unavailable or unobservable calls are never reported as use.
- Keep evidence ownership exact: capability unavailability is owner setup;
  missing, stale, or safely repairable generated evidence is Codex work; and
  unexplained structural drift or unsafe evidence conflicts require human
  review. Never turn a missing Codex-authored evidence row into an instruction
  for the owner to reinstall an already available plugin.
- External runtime skill content is on-demand context, not repository source
  bytes in the 12,000-byte context packet and never canonical project state.
- Codex selects and coordinates the proposed product architecture. AWS Core
  supplies current AWS knowledge, decision guidance, procedures, and execution
  tools. Fastlane governs state, gates, authority, and evidence. The owner
  authorizes; IAM enforces; observed evidence proves what occurred. AWS Core
  never chooses the product architecture or grants authority.
- Apply contract compatibility before rewriting design records. An unchanged approved schema 4 Gate B is grandfathered for its exact design and envelope; do not migrate it, request another approval, or interrupt construction merely because schema 5 exists. A new or unapproved design, or any design-controlled change, requires the complete schema 5 contract, new digests, and fresh Gate B approval.
- A current approved legacy schema 1.2 Gate A is a valid design-only bridge to schema 5. Codex derives `AC-<requirement ID>` labels from approved rows; legacy `NEW_BUILD` uses first-wave journey `NONE` and binds the end-to-end Harness to the wave plus selected approved requirements. Do not rewrite Part I, synthesize owner facts, or ask the owner to repeat them. Route to REQ-10 only for a missing required owner fact or material requirements change; otherwise show `Need from you: Nothing` and continue to Gate B.
- Grandfathering never permits invented schema 5 records, expanded authority, or skipped task, Harness, and evidence validation. It adds no lifecycle stage, owner question, or receipt.
- Follow the current Adaptive Coverage Plan: `SELECT` compares at least two
  complete, credible, non-straw whole-system candidates, `AMEND` reconsiders
  every materially affected driver and
  alternative, and `PRESERVE` is valid only when architecture, technology,
  trust, data, recovery, Region, and Harness boundaries are proven unchanged.
- Derive `DRV-*` records from approved requirements. Compare credible
  whole-system `CAND-*` designs against hard constraints first, then
  preferences. Evaluate a secure managed-serverless baseline for greenfield
  work unless a hard constraint makes it ineligible; never add a straw option
  or use arbitrary numerical scoring.
- Select one eligible `ARCH-*` as an agent recommendation. Record every
  rejected candidate, risk, mitigation, security and reliability impact,
  operational burden, cost effect, scaling breakpoint, migration path, revisit
  trigger, and validation method. Use `NO_VIABLE_ALTERNATIVE` only when
  exactly one candidate satisfies the hard constraints.
- Map every approved requirement to the selected `ARCH-*`, concrete declared
  design IDs, applicable declared property/example IDs, and `AWS-EV-*` IDs. In
  a current schema 5 design, trace IDs resolve only to the selected `ARCH-*`,
  `API/EVENT/CLI/FILE-*` rows in the interface register, `BOUNDARY-*` rows, and
  `STATE-*` rows. `COMP-*`, `DATA-*`, and `CTRL-*` have no current declaration
  surface and therefore fail closed rather than becoming prose-only IDs.
  Property/test trace IDs resolve only to applicable `PROP-*` records present
  across applicability, definition, and execution, or exact `EX-*` rows in the
  Example-based scenarios table. Undeclared `TEST-*` IDs fail closed.
  Each material AWS claim cites its current `AWS-DISC-*`; keep detailed live
  discovery evidence in `docs/project/VERIFY.md`.
- Complete material interfaces and boundaries with numeric bounds or explicit
  `NOT_APPLICABLE - <reason>`, inward dependencies, and server-side authorization.
  Classify lifecycle, async, retry/resume, approval, migration, and meaningful
  state triggers. For `NEW_BUILD`, bind the first wave and any blocking spike;
  spikes use `MAX_ATTEMPTS` and one executable exit command. Give every
  referenced `EX-*` one concrete Example-based scenarios row. Bind that table
  into the modern design digest after Technology and before Property
  applicability, definitions, and execution. Digest all records.

- Complete the Change impact record for `AMEND` or `PRESERVE`. Bind changed,
  affected, and preserved IDs; use `FULL_REVALIDATION` when impact is
  uncertain. It never overrides revision monotonicity or stale-gate rules.
- Complete the Gate B Harness Profile from the selected `TECH-*` register,
  delivery profile, effective risk, data classification, identity boundary,
  public exposure, recovery target, and AWS lane. Give each `HARNESS-*` row one
  exact command or API and an existing VERIFY evidence destination. Use only
  `REQUIRED`, `CONDITIONAL — <trigger>`, or
  `NOT_APPLICABLE — <concrete reason>`; a triggered conditional row is
  required. Select the smallest checks that address the approved risks and do
  not impose a universal scanner.
- Account for this internal applicability checklist in that existing Harness
  Profile: syntax/build; type checking when supported; formatting or
  canonicalization; linting; secret scanning; dependency/SCA; container
  scanning when containers apply; IaC/policy validation when infrastructure or
  policies apply; and license checks when material. Map each concern to
  `REQUIRED` with an exact command, `CONDITIONAL — <trigger>` with an exact
  trigger and command, or `NOT_APPLICABLE — <technology/risk reason>`.
  Do not add a second Harness table, universal tool package, setup dependency,
  Gate B field, lifecycle state, or owner question.
- Evaluate the extended concerns through their canonical Harness rows and
  existing layers: `HARNESS-011` accessibility -> `End-to-end`;
  `HARNESS-012` visual regression -> `End-to-end`; `HARNESS-013` mutation
  testing -> `Unit`; `HARNESS-014` SAST -> `Static`; `HARNESS-015` DAST ->
  `Security and privacy`; and `HARNESS-016` formal/model checking -> `Property`.
  Give each concern its own row, even when two concerns share a layer. Choosing
  applicability is procedural review; deterministic validation begins with the
  recorded row's status, basis, exact command or API, evidence destination, and
  Gate B scope.
- Semantic Anchors remain optional internal vocabulary, not a Fastlane
  dependency or public methodology. Fastlane's local contracts and
  deterministic validators remain authoritative.
- Use ATAM only for a high-risk design with materially competing quality
  attributes. Use a Nygard-style ADR only for a consequential,
  hard-to-reverse decision. Record their conclusions in the existing driver,
  candidate, architecture, ADR, verification, and evidence authorities; do not
  create methodology-specific documents, stages, or gates.
  Selecting and applying ATAM, ADR, or Fagan review is procedural coordinator
  review; deterministic validation covers the resulting current PRD records,
  traceability, and digests, not proof that the review method itself occurred.
- Keep method names internal. Explain them only when the owner explicitly asks;
  routine owner questions remain short and plain-language.
- Use the architecture challenger only after the proposal is complete and only
  for hard-to-reverse, shared-infrastructure, isolation, recovery, material
  risk, or explicitly requested review. Attempt once per exact design revision.
  Allow 10 minutes for Quick MVP or Standard and 45 minutes for high-risk or
  explicit deep review. Check progress at least every 60 seconds and finish
  early.
- Require the challenger to return unsupported claims, unmet requirements,
  hard-constraint failures, IAM/isolation/recovery/cost/operations gaps, and
  concerns with rejected alternatives using current IDs. The coordinator fixes
  valid findings or records an evidence-backed rejection.
- The coordinator accepts or rejects each finding with evidence, updates
  existing Mermaid diagrams in place with the selected `ARCH-*` as their
  shared basis, and remains the sole writer.
- Require a current Gate A, complete readiness card, canonical construction
  envelope digest, selected architecture, complete traceability, current
  material AWS evidence, complete Harness Profile and change impact, and exact
  owner Gate B receipt.
- For every authenticated AWS lane, author the Gate B `AWS allowed operations`
  row as the deduplicated maximum union of exact operations needed across the
  applicable AWS-10, AWS-20, AWS-30, AWS-40, and AWS-50 phases. Later execution
  may use only the intersection of that maximum, the current phase mode, and
  current phase-specific authority. An explicit-gate
  `MUTATE_LISTED_RESOURCES` maximum never authorizes deployment or teardown by
  itself.
