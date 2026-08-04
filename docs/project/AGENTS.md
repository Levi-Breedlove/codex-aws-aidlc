# Project document rules

This guide narrows the root rules and never widens approval or authorization.

- Preserve one canonical PRD, task ledger, evidence record, and runbook. Never create separate human and machine copies.
- Begin each canonical project document with its title, one ownership sentence, one Engine-derived `Current state` table, and one short navigation list. Keep that first screen to 25-40 visible nonblank lines, show exactly one owner need or `Nothing`, what Codex does next, and what remains unapproved or unauthorized.
- Project facts and owner decisions belong here. Codex procedures belong in phase references; receipt syntax in the prompt registry; enum, digest, sorting, and routing behavior in the Engine and tests.
- Preserve parser-controlled headings, table headers, stable IDs, record order, marked receipts, and appendices. Change a contract and its parser, migration, digest, selectors, and tests atomically.
- Owner-facing summaries and body explanations are generated, non-authoritative views bounded by `FASTLANE:DOCUMENT_SUMMARY` and `FASTLANE:HUMAN_VIEW` markers. Canonical parsers, context, routing, and every requirements, design, diagram, task, evidence, gate, and authority digest exclude both complete blocks. A stale view is safe Codex repair and may block a misleading brief, but never stales a gate itself.
- Count a nonblank rendered line outside a closed `<details>` body as visible; count its `<summary>` once. Keep Product Agreement within 45 visible PRD lines, active task progress within 35 TASKS lines, populated claims within 30 VERIFY lines, and the operator path within 45 RUNBOOK lines.
- Use balanced, labeled `<details>` only for appendices or exact records. Never collapse the current action, material risk, project command, project diagram, readiness summary, approval boundary, or the Gate A and Gate B receipts. Audit copies of conditional AWS receipts may be disclosed because the exact current action receipt is presented in chat when ready.
- Raw file length is not the readability measure. Keep visible nonblank lines at or below PRD 330, TASKS 65, VERIFY 90, RUNBOOK 220, and BUGFIX 90 while retaining complete canonical records. PRD, TASKS, VERIFY, and RUNBOOK together must be at least 20,000 characters shorter than the 1.2.3 baseline.
- Keep hashes, receipt grammar, schema/parser/routing rules, EARS, QAS, Harness, and context-management procedure outside the ordinary owner reading path.
- Project Mermaid blocks express planned design. Bind them through the Diagram Contract; never treat a diagram as implementation, deployment, evidence, or authority.
- VERIFY contains observed evidence; RUNBOOK contains operational procedures/facts. Never persist credentials, raw transcripts, local paths, context packets, plugin/trust state, or ephemeral prerequisite evidence.
- Codex remains the sole writer. Challengers are read-only and cannot change these files.
