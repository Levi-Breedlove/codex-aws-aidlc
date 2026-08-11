---
name: fastlane
description: Coordinate Fastlane initialization, requirements, design, tasks, and local verification. Use for init template, resume, planning, or approved construction.
---

# Fastlane Coordinator

You are the single coordinator and sole writer.

1. Read root and applicable nested `AGENTS.md` files.
2. Inspect `bootstrap.yaml` before running setup or printing a welcome.
   - An initialized project skips prerequisites and setup questions, then
     resumes from the Fastlane Engine.
   - An untouched template runs `python scripts/setup_assistant.py
     prerequisites --root . --json`. Supply only allowlisted, ephemeral
     official AWS Core capability observations through `--evidence-stdin`.
     If blocked, return its complete checklist unchanged and stop.
   - After `PREREQUISITES_READY`, run `python scripts/setup_assistant.py
     welcome`. Return its complete stdout verbatim as the entire owner response;
     do not alter it. It already asks exactly once
     for project name, preferred Region, and optional budget. Initialize
     dry-run-first, then continue to the Engine. After initialization, render
     `python scripts/fastlane_presenter.py project-ready --input-stdin` once;
     never on resume.
3. Run `python scripts/bootstrap_doctor.py --root . --json`. This stable CLI
   delegates to the modular Fastlane Engine. Treat its `interaction` and
   `remediation` objects as the only routing and next-action state; do not
   import or reinterpret internal domain policy.
   During Define, the presenter binds `intake_foundation.next_question_guidance`
   to one natural question, why it matters, and what its answer changes.
   Use `intake_foundation.project_configuration` for Codex-owned internal
   classification. Never ask the owner to select project mode, delivery
   profile, effective risk, or AWS lane. When `codex_actions` are present,
   derive and synchronize those canonical values from the cited owner facts,
   use the projected project mode and safest current AWS lane, and rerun the
   Engine before continuing requirements analysis.
4. Follow the Engine's `context_plan`. Load only the exact ranges in
   `resolved_initial_slices`; their canonical source bytes and digests measure
   repository content, not total model context. Treat `maximum_initial_bytes`
   and `maximum_initial_source_bytes` as the same source-byte budget. Honor `WITHIN_LIMIT`, include
   the one complete listed record for `OVERSIZED_REQUIRED_RECORD` without an
   owner action, and route `SOURCE_INVALID` through remediation. Load
   `resolved_on_demand_slices` only when required. Never silently truncate a row
   or required record. Never persist or treat a packet as authority.
5. Phase references are not implicit context. Load one only when named in
   `resolved_initial_slices` or `resolved_on_demand_slices`:
   - BOOT/INTAKE/REQ/Gate A: `references/define.md`
   - explicit owner brief: `references/source-assisted-define.md`
   - DESIGN/Gate B: `references/design.md`
   - TASK/BUILD/RELEASE: `references/deliver.md`
6. Load `references/owner-responses.md` only when presenting an owner update.
   Load `references/authorization-receipts.md` only at a formal gate or
   external-authorization boundary.
   Setup renderer output is final owner copy; never translate it.
   Owner-facing responses are technical consultation, not raw state relay.
   Translate validated projections into practical consequences,
   evidence-backed recommendations when justified, principal tradeoffs, and
   one next action without changing the projected state, evidence maturity, or
   authority.
7. Read only the canonical prompt section selected by the Engine. Stable prompt
   IDs are routing metadata, not owner instructions. BUG-10 and SYNC-10 are the
   only current-request-scoped adjunct prompts: invoke one only when the current
   owner message explicitly requests its bounded analysis or named GitHub
   reconciliation and current authority permits every write. Preserve the
   Engine-derived route and pending owner action, run only the adjunct's allowed
   work, rerun the Engine, and return to its derived route. An adjunct cannot
   replace a lifecycle phase, cross a gate, create authority, or become a
   persisted next prompt.
8. Render routine updates with `python scripts/fastlane_presenter.py owner
   --input-stdin`. Run, validate, checkpoint, and rerun the Engine in the same
   turn while `automatic_continuation_allowed` is true.
   At checkpoints, repair `DOCUMENT_SUMMARY_STALE` only from the module's exact
   marked block, then rerun the Engine. Never hand-author it; other diagnostics fail closed.

   `references/owner-responses.md` owns deterministic intake parsing, Answer
   Confirmation, turn boundaries, side questions, corrections, Owner Decision
   Briefs, navigation, and receipt presentation. Follow it exactly; never
   hand-compose or persist a competing owner-facing state.

   For safe `AGENT_CORRECTION`, fix only in-bound generated defects, validate,
   and rerun the Engine. Never rewrite owner facts, approved requirements,
   architecture/technology, gates, receipts, authority, protected paths, or
   external state. Manual safety blocks automatic repair; mixed items repair
   only independent Codex items before deriving the remaining action.

   For an immediate safe correction, rerun exactly once with
   `python scripts/bootstrap_doctor.py --root . --json --prior-remediation-fingerprint
   <report.remediation.fingerprint>`. Pass it only to this immediate next Engine
   invocation and never persist it. If the same fingerprint remains, route the
   resulting human safety review.

   During AWS delivery explicitly use `operate-fastlane-aws` and obey
   `aws_execution.progress_state`; that skill owns operations and the journal,
   while the prompt registry owns receipts and the Engine owns state/authority.
   Mention AWS Core in `Audit:` only for the validated `search_documentation` then matching `retrieve_skill` chain; caller prose,
   plugin availability, and cached content are not evidence.
9. After recording an accepted Gate A or Gate B receipt, rerun the Engine
   immediately. Gate A continues into Design. Gate B continues into task
   generation and permitted local construction.
   Gate A readiness requires the current requirements-contract projection;
   Gate B readiness requires the current design-contract projection, including
   material interfaces, boundaries, states, diagram contract, and approved first wave.


For a side question, answer directly without state change unless requested.
Rerun the Engine, then use
`scripts/fastlane_presenter.py side-question --input-stdin` to restore the
pending action. Explaining current questions is clarification, not learning:
explain practical consequences, say state is unchanged, and restore the same
choices. Route teaching Fastlane itself to `explain-fastlane`.

Stop only for an owner decision or gate, human safety review, stale/conflicting
scope, missing material evidence, an exhausted correction or write boundary,
or missing external authority. Safely agent-correctable validation failures
continue automatically.

`Maximum workers: 1` limits task claims and mutation; one synchronous read-only
critique at its defined checkpoint is not a worker. It claims no task and
changes no state. Start a requirements challenge only after the complete draft
with no open owner decision; attempt once per exact revision. Quick MVP uses none by
default; when material risk justifies one, allow 5/10 minutes for requirements/
architecture. Standard uses 5/10; high-risk or explicit deep review uses 30/45.
Check at least every 60 seconds and finish early. If unavailable, stop it, note
that in the Gate A recommendation rationale, perform the coordinator checklist,
rerun the Engine and presenter, and continue. Never narrate reviewer availability
or make it an owner action. These restrictions propagate: challengers and their
descendants cannot write, claim tasks, choose architecture, mutate state,
approve, authorize, satisfy AWS evidence, or operate AWS.

Never install software, alter Codex/plugin state, inspect credentials, access
an AWS account during planning, persist prerequisite observations, or
interpret tool availability as authority.
