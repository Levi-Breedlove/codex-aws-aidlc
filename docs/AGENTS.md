# Fastlane documentation guide

This guide narrows the root rules and never widens approval or authorization.

## Audience and purpose

- `README.md`, `docs/README.md`, `SETUP.md`, `WORKFLOW.md`,
  `TROUBLESHOOTING.md`, and `HOOKS.md` are human-facing.
- `DEPENDENCY-POLICY.md` and `EVALUATION.md` are readable maintainer guides.
- `docs/project/` holds the one canonical set of project records. Follow its
  nested guide before changing those templates.

## Human-facing writing

- Lead with what Fastlane does, what the reader needs to do, and what happens
  next.
- Use plain language for choices, consequences, safety boundaries, and claim
  maturity. Define a necessary technical term at first use.
- Keep setup and troubleshooting commands copyable and platform-specific.
- Preserve working repository-relative links, stable headings, and Mermaid
  diagrams. Never present a planned diagram as observed evidence.
- Do not place parser, digest, schema-migration, routing, EARS, QAS, Harness,
  or context-packet procedure in an ordinary owner reading path.

## Instruction authority

- Root `AGENTS.md` owns global invariants and lifecycle boundaries.
- Fastlane phase references own Define, Design, and Deliver procedures.
- `prompts/CODEX-PROMPTS.md` owns exact receipts and prompt syntax.
- The Engine and tests own deterministic schemas, parsing, routing, and hashes.
- `.codex/hooks/AGENTS.md` owns hook implementation invariants.
- `maintain-fastlane` references own documentation and evaluation procedures.

Do not create a second PRD, task ledger, evidence ledger, runbook, approval
record, or other competing source of truth. Human summaries are views of the
canonical records, never replacement records.
