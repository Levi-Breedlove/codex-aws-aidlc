# Design phase

Use for DESIGN-10 and Gate B.

- Complete the whole-system architecture, security, data, failure, recovery,
  operations, cost, deployment, rollback, teardown, and verification design.
- Use official current AWS Core directly for material current AWS facts and
  record attributable documentation evidence. Generic connectors, memory, or
  challenger prose cannot replace those calls.
- Follow the current Adaptive Coverage Plan: `SELECT` compares complete
  architectures, `AMEND` reconsiders every materially affected driver and
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
- Map every approved requirement to the selected `ARCH-*`, concrete
  `COMP/API/DATA/CTRL` IDs, applicable property/test IDs, and `AWS-EV-*` IDs.
  Keep detailed live AWS Core invocation evidence in `docs/project/VERIFY.md`.
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
- Use ATAM only for a high-risk design with materially competing quality
  attributes. Use a Nygard-style ADR only for a consequential,
  hard-to-reverse decision. Record their conclusions in the existing driver,
  candidate, architecture, ADR, verification, and evidence authorities; do not
  create methodology-specific documents, stages, or gates.
- Keep method names internal. Explain them only when the owner explicitly asks;
  routine owner questions remain short and plain-language.
- Use the architecture challenger only after the proposal is complete and only
  for high-risk, hard-to-reverse, shared-infrastructure, isolation, recovery,
  or explicitly requested review.
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
