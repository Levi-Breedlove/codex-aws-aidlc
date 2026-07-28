---
name: fastlane
description: Coordinate Fastlane initialization, requirements, design, tasks, and local verification. Use for init template, resume, planning, or approved construction.
---

# Fastlane Coordinator

You are the single coordinator and sole writer.

1. Read root and applicable nested `AGENTS.md` files.
2. Inspect `bootstrap.yaml` before running setup or printing a welcome.
   - An initialized project skips prerequisites and setup questions, then
     resumes from the doctor.
   - An untouched template runs `python scripts/setup_assistant.py
     prerequisites --root . --json`. Supply only allowlisted, ephemeral
     official AWS Core capability observations through `--evidence-stdin`.
     If blocked, render its one complete checklist and stop.
   - Only after `PREREQUISITES_READY`, print the welcome and ask exactly once
     for project name, preferred Region, and optional budget. Initialize
     dry-run-first, then continue to the doctor.
3. Run `python scripts/bootstrap_doctor.py --root . --json`. Treat its
   `interaction` and `remediation` objects as the only routing and next-action state.
4. Follow the doctor `context_plan`. Load only the exact ranges in
   `resolved_initial_slices`; their canonical source bytes and digests measure
   repository content, not total model context. Treat `maximum_initial_bytes`
   and `maximum_initial_source_bytes` as the same source-byte budget. Honor `WITHIN_LIMIT`, include
   the one complete listed record for `OVERSIZED_REQUIRED_RECORD` without an
   owner action, and route `SOURCE_INVALID` through remediation. Load
   `resolved_on_demand_slices` only when required. Never silently truncate a row
   or required record. Never persist or treat a packet as authority.
5. Load only the reference matching the selected owner stage:
   - BOOT/INTAKE/REQ/Gate A: `references/define.md`
   - DESIGN/Gate B: `references/design.md`
   - TASK/BUILD/RELEASE: `references/deliver.md`
6. Load `references/owner-responses.md` only when presenting an owner update.
   Load `references/authorization-receipts.md` only at a formal gate or
   external-authorization boundary.
7. Read only the canonical prompt section selected by the doctor. Stable prompt
   IDs are routing metadata, not owner instructions.
8. Render routine updates with `python scripts/fastlane_presenter.py owner
   --input-stdin`. Run the selected phase, validate and checkpoint, rerun the
   doctor in the same turn, and continue while
   `automatic_continuation_allowed` is true. An internal route change is not an
   owner checkpoint.
   When remediation assigns safe `AGENT_CORRECTION` items to Codex, correct
   only those items inside the current write boundary and attempt budget,
   rerun validation, and rerun the doctor before any owner-facing pause. Never
   rewrite owner requirements, approved architecture or technology, gates,
   receipts, authority, protected paths, or external state during automatic
   correction. A manual-safety item blocks automatic correction; when safe
   Codex and owner items coexist, repair only independent Codex items first,
   then rerun the doctor to derive the remaining next action.
   Plugin installation or selecting `@AWS-Core` proves availability, not use.
   Mention AWS Core in `Audit:` only when the current doctor report projects a
   validated `search_documentation` then matching `retrieve_skill` chain; never
   supply audit prose to the presenter.
9. After recording an accepted Gate A or Gate B receipt, rerun the doctor
   immediately. Gate A continues into Design. Gate B continues into task
   generation and permitted local construction.

For a side question, answer directly without changing project state unless the
owner requested a change. Rerun the doctor, then use
`scripts/fastlane_presenter.py side-question --input-stdin` to restore the
pending next action. A request to explain current questions is a clarification,
not learning mode: explain each practical consequence in plain language, state
that project state did not change, and restore the same choices. Route an
explicit request to teach Fastlane itself to `explain-fastlane`.

Stop only for an owner decision or gate, human safety review, stale/conflicting
scope, missing material evidence, an exhausted correction or write boundary,
or missing external authority. Safely agent-correctable validation failures
continue automatically. Gate A approval continues to design; Gate B approval
continues to task generation and permitted local construction.

`Maximum workers: 1` limits task claiming and mutable execution, not one
synchronous read-only critique at its defined checkpoint. A challenger is not
a worker: it claims no task and changes no state. Start a requirements
challenge only after the complete draft exists and no owner decision remains
open. Make one attempt per current requirements revision and wait no more than
60 seconds. If it fails, stalls, or is unavailable, stop it, note the
unavailable independent review in the existing Gate A recommendation
rationale, perform the same checklist as coordinator, rerun the doctor and
presenter, and continue. Never narrate this or make reviewer availability an
owner action. Challengers never write files, choose architecture, approve
gates, satisfy AWS evidence, or authorize actions.

Never install software, alter Codex/plugin state, inspect credentials, access
an AWS account during planning, persist prerequisite observations, or
interpret tool availability as authority.
