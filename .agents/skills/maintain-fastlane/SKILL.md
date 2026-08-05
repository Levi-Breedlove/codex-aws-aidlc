---
name: maintain-fastlane
description: Maintain Fastlane prompts, scripts, skills, manifests, packaging, or CI. Use only for framework work, never adopter application planning.
---

# Maintain Fastlane

This skill governs work on the reusable Fastlane framework. It never starts
BOOT, INTAKE, DESIGN, BUILD, or another adopter lifecycle route.

## Select one maintenance mode

- `AUDIT` is read-only inspection and validation. It may run non-mutating
  checks and returns observed evidence and bounded findings.
- `PLAN` is read-only analysis that returns a decision-complete implementation
  plan. It does not edit, commit, or publish.
- `IMPLEMENT` permits local edits only. It does not imply commit, push, pull
  request, merge, branch deletion, release, or other publication authority.
- `PUBLISH` performs only the exact separately authorized Git operation or
  release action. Publication authority never implies implementation authority
  or permission for another publication action.

Review, audit, inspect, analyze, and plan requests default to `AUDIT` or
`PLAN`. Change, fix, refactor, and implement requests use `IMPLEMENT` only when
the scope contract below is complete. Commit, push, PR, merge, branch deletion,
tag, and release actions require explicit `PUBLISH` authority naming each
permitted operation and target.

## Scope contract

Before `IMPLEMENT`, record all of:

- baseline branch and exact commit;
- intended outcome;
- explicit non-goals;
- exact file allowlist;
- observable acceptance criteria; and
- maximum changed files and target net production lines.

If any field is missing, stop with one bounded request for the missing scope.
Do not infer it from an adopter lifecycle, previous conversation, or unrelated
repository state. Stop before widening the allowlist, outcome, authority, or
change budget.

Before changing public or project-record documentation, read
`references/documentation-governance.md` in full. Before evaluation,
qualification, pilot, or release-claim work, read `references/evaluation.md` in
full. Before final package, CI, rendered-review, or release qualification, also
read `references/qualification.md` in full. These references consolidate
maintainer procedure; they do not create
project authority or another lifecycle.

## Procedure

1. Confirm the request targets the framework and select the maintenance mode.
2. Read root and scoped `AGENTS.md` files. Lock the checked-out baseline and
   preserve unrelated work.
3. Keep lifecycle, receipts, authorization, and package boundaries
   deterministic; skills guide while scripts validate exact state.
   Any Semantic Contract change updates its workflow guidance, applicable
   phase procedure, PRD schema, validator/router, owner-visible presentation
   when affected, tests, and manifest in the same bounded change.

4. Before `IMPLEMENT` or `PUBLISH`, validate the ephemeral scope contract with
   `python scripts/maintenance_preflight.py --contract <contract.json> --root . --json`.
   The preflight is read-only; keep the contract outside tracked product state.
   Then make the smallest coherent change and direct regression tests inside the
   validated scope. Unrelated discoveries are report-only.
5. For bounded framework or brownfield refactoring, use the Mikado Method:
   attempt the smallest target change; identify a blocking prerequisite;
   preserve or revert unsafe exploratory edits; implement only the in-scope
   prerequisite; return to the original goal; and report unrelated discoveries
   without absorbing them. Mikado is not a lifecycle phase or task state.
6. Refresh `bootstrap.manifest.json` only after source edits are final. Run
   focused tests, the full suite, manifest and deterministic package checks,
   and `git diff --check` before any authorized publication.
7. For canonical customer-package maintenance, compare current package bytes
   and inventory with one exact existing ancestor by running `python
   scripts/package_release.py --check --base-commit <exact-base-commit>`.
   Package changes require a strictly greater semantic version in
   `bootstrap.manifest.json` and synchronized mirrors. The guard is read-only,
   never fetches or publishes, and fails closed without the exact history. It
   does not apply Fastlane framework-version rules to initialized adopter
   application changes.

## Live customer publication

For the live `fast-lane` customer branch, `PUBLISH` defaults to a
PR-gated flow:

1. create a short-lived maintenance branch from the exact current customer tip;
2. push only that short-lived branch and open a pull request targeting only
   `fast-lane`;
3. require the pull request branch to be current with the customer tip; and
4. merge only after all of these exact checks pass:
   - `safety-tests (3.11)`;
   - `safety-tests (3.12)`;
   - `safety-tests (3.13)`;
   - `windows-smoke`; and
   - `macos-setup-smoke`.

A direct push to `fast-lane` requires explicit emergency publication
authorization naming that branch and push. Never force-push or delete the
live customer branch. Configuring or changing its GitHub branch rule is a
separate repository-setting action and is not implied by source publication.
The protected `fast-lane-foundation` branch preserves the 1.0.5 predecessor
and remains outside this customer flow unless separately authorized.

Every `PUBLISH` operation must revalidate the exact source and target branch
tips and commits immediately before mutation. Never switch, reset, merge,
force-push, delete, or release outside the exact owner authorization.

Never install software, change Codex/plugin state, inspect credentials, access
an AWS account, approve a gate, or publish beyond the owner's exact scope.
