# Fastlane Engine scope

This package owns read-only observation, parsing, validation, routing, and
derived projections. Canonical Markdown remains authoritative.
This guide narrows the root rules and never widens approval or authorization.

- Domain evaluators consume immutable inputs. They do not read files, run Git,
  invoke subprocesses, access a network, or write state.
- `core.snapshot` is the only normal read-only filesystem observation boundary.
- `core` imports no lifecycle domain. `package` imports only `core`.
- Lifecycle domains do not import sibling lifecycle domains.
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
