# Documentation governance procedure

Use this reference for changes to public Fastlane documentation or canonical
project-record templates. It is a maintenance procedure, not an adopter phase.

## Authority map

| Content | Canonical home |
|---|---|
| Product introduction and quick start | `README.md` |
| Human documentation navigation | `docs/README.md` |
| Setup and owner-run prerequisites | `docs/SETUP.md` |
| Human lifecycle and gate explanation | `docs/WORKFLOW.md` |
| Troubleshooting | `docs/TROUBLESHOOTING.md` |
| Optional hook activation | `docs/advanced/HOOKS.md` |
| Maintainer evaluation overview | `docs/maintainers/EVALUATION.md` |
| Release qualification procedure | `references/qualification.md` |
| Global agent invariants | root `AGENTS.md` |
| Phase procedures | Fastlane Define, Design, and Deliver references |
| Exact receipts and prompt syntax | `prompts/CODEX-PROMPTS.md` |
| Hook implementation invariants | `.codex/hooks/AGENTS.md` |
| Schemas, parsing, digests, sorting, and routing | Engine and tests |
| Current adopter-project facts | `docs/project/` canonical records |

Never duplicate authority to make a document easier to read. Improve the view,
navigation, labels, disclosure structure, or generated summary while preserving
the single canonical record.

## Review method

1. Identify the document's primary reader and first action.
2. Keep the first screen focused on current state, owner need, next Codex action,
   and unapproved or unauthorized work.
3. Relocate machine procedure to its canonical instructional home. Preserve any
   parser-controlled heading, table, marker, stable ID, receipt, and record order.
4. Keep active decisions, material risks, commands, diagrams, and formal receipts
   open. Use balanced labeled disclosures only for exact records or appendices.
5. Validate all relative links, heading anchors, Mermaid fences, summary markers,
   UTF-8 text, visible-line budgets, package inventory, and version mirrors.

Count a visible line as a nonblank rendered line outside a closed `<details>`
body; count its `<summary>` once. Machine terminology in an exact collapsed
record is allowed when the parser requires it, but it must not leak into the
ordinary owner path.

Any Semantic Contract change must update workflow guidance, the applicable
phase procedure, project schema, Engine validation/projection, owner-visible
presentation, focused tests, compatibility handling, version mirrors, and the
manifest in one bounded change.
