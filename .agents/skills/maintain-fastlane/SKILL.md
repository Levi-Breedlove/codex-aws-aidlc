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

## Procedure

1. Confirm the request targets the framework and select the maintenance mode.
2. Read root and scoped `AGENTS.md` files. Lock the checked-out baseline and
   preserve unrelated work.
3. Keep lifecycle, receipts, authorization, and package boundaries
   deterministic; skills guide while scripts validate exact state.
4. For `IMPLEMENT`, make the smallest coherent change and direct regression
   tests inside the scope contract. Unrelated discoveries are report-only.
5. For bounded framework or brownfield refactoring, use the Mikado Method:
   attempt the smallest target change; identify a blocking prerequisite;
   preserve or revert unsafe exploratory edits; implement only the in-scope
   prerequisite; return to the original goal; and report unrelated discoveries
   without absorbing them. Mikado is not a lifecycle phase or task state.
6. Refresh `bootstrap.manifest.json` only after source edits are final. Run
   focused tests, the full suite, manifest and deterministic package checks,
   and `git diff --check` before any authorized publication.

`PUBLISH` must revalidate the exact branch tip and commit immediately before
mutation. Never switch, reset, merge, force-push, delete, or release outside
the exact owner authorization.

Never install software, change Codex/plugin state, inspect credentials, access
an AWS account, approve a gate, or publish beyond the owner's exact scope.
