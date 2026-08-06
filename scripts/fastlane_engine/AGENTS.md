# Fastlane Engine scope

This package owns read-only observation, parsing, validation, routing, and
derived projections. Canonical Markdown remains authoritative.
This guide narrows the root rules and never widens approval or authorization.

- Domain evaluators consume immutable inputs. They do not read files, run Git,
  invoke subprocesses, access a network, or write state.
- `core.snapshot` is the only normal read-only filesystem observation boundary.
- `core` imports no lifecycle domain. `package` imports only `core`.
- Lifecycle domains do not import sibling lifecycle domains.
- `define/` owns intake, requirements, assumptions, adaptive coverage, change
  impact, brownfield safeguards, AWS materiality, and Gate A readiness. It
  consumes observed text and explicit caller policy; it cannot approve Gate A.
- `design/` owns architecture comparison, technology and property support,
  source disposition, Harness selection, project interfaces and state models,
  diagrams, the construction envelope, and optional ADR rationale evaluation.
  Define projections and the invocation clock are explicit inputs; Design
  cannot approve Gate B or grant construction or external authority.
- ADR file inventory and bounded reads remain in `../fastlane_adr.py`; the
  Design evaluator consumes only repository-relative observed sources. ADRs
  remain supporting rationale and never enter requirements or design digests.
- `deliver/` owns task, evidence, checkpoint, repository, and release
  validation over already-observed records. It cannot mutate task state, run
  Git, claim work, publish, or grant construction or external authority.
- `aws/` owns AWS Core evidence plus preflight, deployment, reconciliation,
  residual-review, and teardown state machines over already-observed records.
  It accepts current authority as an explicit input, performs no AWS call, and
  cannot expand resources, operations, time, cost, or receipt scope.
- Routing consumes domain results, never parsers or snapshot builders.
- Reporting serializes already-derived results and does not make policy.
- Exact ordering, IDs, hashes, receipts, diagnostics, and compatibility behavior
  are canonicalization or safety contracts. Preserve them byte-for-byte unless
  an approved migration changes the contract.
- Presenter, hooks, initialization, task mutation, GitHub actions, and AWS
  operations remain outside this package.
- New modules must be packaged and protected by every control inventory.

Comments should explain only authority, safety, compatibility, or
canonicalization. Do not add generic helpers or catch-all modules.
