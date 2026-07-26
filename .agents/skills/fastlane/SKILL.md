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
4. Follow the doctor `context_plan`. Load the complete selected rows or records
   from `source_slices`, filtered to `active_ids`, without exceeding
   `maximum_initial_bytes`. Never silently truncate a row or blocking record.
   Load `on_demand_slices` only when the current decision or validator requires
   them. Context packets are ephemeral views and never become authority or
   tracked project state.
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
9. After recording an accepted Gate A or Gate B receipt, rerun the doctor
   immediately. Gate A continues into Design. Gate B continues into task
   generation and permitted local construction.

For a side question, answer directly without changing project state unless the
owner requested a change. Rerun the doctor, then use
`scripts/fastlane_presenter.py side-question --input-stdin` to restore the
pending next action. Route an explicit teaching request to `explain-fastlane`.

Stop only for an owner decision or gate, human safety review, stale/conflicting
scope, missing material evidence, an exhausted correction or write boundary,
or missing external authority. Safely agent-correctable validation failures
continue automatically. Gate A approval continues to design; Gate B approval
continues to task generation and permitted local construction.

Optional requirements and architecture challengers are read-only critics at
their defined checkpoints. They never write files, choose the proposal,
approve gates, satisfy AWS evidence, or authorize external actions.

Never install software, alter Codex/plugin state, inspect credentials, access
an AWS account during planning, persist prerequisite observations, or
interpret tool availability as authority.
