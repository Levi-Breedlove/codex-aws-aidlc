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
     If blocked, render its one complete checklist and stop.
   - Only after `PREREQUISITES_READY`, print the welcome and ask exactly once
     for project name, preferred Region, and optional budget. Initialize
     dry-run-first, then continue to the Engine.
3. Run `python scripts/bootstrap_doctor.py --root . --json`. This stable CLI
   delegates to the modular Fastlane Engine. Treat its `interaction` and
   `remediation` objects as the only routing and next-action state; do not
   import or reinterpret internal domain policy.
4. Follow the Engine's `context_plan`. Load only the exact ranges in
   `resolved_initial_slices`; their canonical source bytes and digests measure
   repository content, not total model context. Treat `maximum_initial_bytes`
   and `maximum_initial_source_bytes` as the same source-byte budget. Honor `WITHIN_LIMIT`, include
   the one complete listed record for `OVERSIZED_REQUIRED_RECORD` without an
   owner action, and route `SOURCE_INVALID` through remediation. Load
   `resolved_on_demand_slices` only when required. Never silently truncate a row
   or required record. Never persist or treat a packet as authority.
5. A phase reference is not an implicit initial load. Use this mapping only to
   identify the relevant procedure; load it initially only when it appears in
   `resolved_initial_slices`, or later from `resolved_on_demand_slices` when the
   current decision or validation requires it:
   - BOOT/INTAKE/REQ/Gate A: `references/define.md`
   - DESIGN/Gate B: `references/design.md`
   - TASK/BUILD/RELEASE: `references/deliver.md`
6. Load `references/owner-responses.md` only when presenting an owner update.
   Load `references/authorization-receipts.md` only at a formal gate or
   external-authorization boundary.
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


For a side question, answer directly without changing project state unless the
owner requested a change. Rerun the Engine, then use
`scripts/fastlane_presenter.py side-question --input-stdin` to restore the
pending next action. A request to explain current questions is a clarification,
not learning mode: explain each practical consequence in plain language, state
that project state did not change, and restore the same choices. Route an
explicit request to teach Fastlane itself to `explain-fastlane`.

Stop only for an owner decision or gate, human safety review, stale/conflicting
scope, missing material evidence, an exhausted correction or write boundary,
or missing external authority. Safely agent-correctable validation failures
continue automatically.

`Maximum workers: 1` limits task claiming and mutable execution, not one
synchronous read-only critique at its defined checkpoint. A challenger is not
a worker: it claims no task and changes no state. Start a requirements
challenge only after the complete draft exists and no owner decision remains
open. Attempt once per exact requirements revision. Quick MVP uses no challenger by default;
when material risk justifies one, allow 5 minutes for requirements and 10 for
architecture. Standard uses 5/10 minutes. High-risk or explicit deep review
uses 30/45 minutes. Check progress at least every 60 seconds and finish early.
If it fails, stalls, or is unavailable, stop it, note the unavailable
independent review in the existing Gate A recommendation
rationale, perform the same checklist as coordinator, rerun the Engine and
presenter, and continue. Never narrate this or make reviewer availability an
owner action. Challengers never write files, choose architecture, approve
gates, satisfy AWS evidence, or authorize actions. These restrictions propagate
to every descendant subagent; a read-only challenger cannot spawn a writer,
task claimant, state mutator, approver, authorizer, or AWS operator.

Never install software, alter Codex/plugin state, inspect credentials, access
an AWS account during planning, persist prerequisite observations, or
interpret tool availability as authority.
