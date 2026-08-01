# Owner responses

- Lead with plain-language project status, not internal execution narration.
- Render routine status with `python scripts/fastlane_presenter.py owner
  --input-stdin`; do not hand-compose lifecycle routing.
- Present one concrete next action. Show an owner action only for a genuine
  decision, setup step, approval, authorization, protected-boundary decision,
  or human safety review. Otherwise continue the selected phase.
- Do not expose hashes, file counts, prompt IDs, or exhaustive receipts in
  routine conversation.
- Never accept self-asserted audit prose. After observable current AWS Core
  `search_documentation` and matching `retrieve_skill` evidence, let the
  presenter name the returned skill identifier and official references, then
  state that no AWS account was accessed. If those calls are unavailable or
  unobservable, omit `Audit:` rather than claiming AWS Core use. Persist no raw
  skill content, transcript, credential, session identifier, or machine detail.
- Keep the AWS delivery states distinct. Guidance needs nothing from the owner
  and accesses no account. Read-scope authorization tells the owner the named
  account will be accessed read-only. Running preflight needs no further owner
  action. Observed readiness leads to the separate mutation decision only when
  the lane can mutate. Never describe documentation guidance as authenticated
  preflight or a read receipt as deployment authority.
- Answer side questions directly, state whether project state changed, and
  restore the pending next action with `python scripts/fastlane_presenter.py
  side-question --input-stdin` after rerunning the Engine.
- A side question never repeats a formal Gate A, Gate B, or AWS receipt. It
  restores the current deterministic next action, including an existing owner
  approval when one is pending.
- A pre-Gate-A AWS example must say:
  `Illustrative architecture candidate — not selected or approved.`
- Use `explain-fastlane` only for an explicit explanation request.
- Before writing a Gate A or Gate B owner record, validate the complete
  candidate with `python scripts/bootstrap_doctor.py --root .
  --validate-gate-receipt --input-stdin --json`. Only a `PASS` result may be
  recorded. On `FAIL`, write nothing, tell the owner that no approval was
  recorded, preserve the same pending gate, and show the unchanged exact
  current receipt again without echoing the rejected input. A formatting error
  does not route backward; only an independently reported material change or
  stale basis returns to requirements or design.

## Plain-language decisions
For guided intake, render only the current Engine-validated
`INTAKE-CARD-*`. Use its stable reply keys, uppercase A/B/C decision choices,
required-detail prompts, and plain `owner_reply`. Do not expose its internal
ID, revision, digest, or legacy reply token. The parser receives the exact card
identity separately before any write; retain `R-*` only as an internal 1.0.x
compatibility input for that same current card. Factual questions remain short
free text. Recommend a choice
only when current evidence justifies it; there is no universal default. If no
recommendation is justified, render exactly
`No recommendation—choose the option that matches your situation.` and use
`1: <choose A, B, or C>` for that decision in the copyable reply. Rendering a card with
`turn_boundary_required` ends the assistant turn; only a new owner message
may resolve it.

- Explain the real-world consequence before a technical name or abbreviation.
  Keep precise engineering terms in canonical records, but do not require the
  owner to know them.
- Unless the owner already used the term or asks for technical detail, translate
  `RTO` into how quickly service returns after an outage, `RPO` into how much
  recent data might need recovery, `p95` into “at least 95 out of every 100
  requests,” concurrency into people using the product at the same time, and
  metadata into concrete examples such as hidden location and device details.
- After the three initial settings, present exactly one numbered intake question. For a decision, mark one
  `Recommended` choice only when justified, state its principal benefit or
  limitation, and offer no more than two understandable alternatives. Do not
  label factual questions as decisions. Use `1 question remains before
  requirements analysis.` when only one question is pending.
- End input requests with one short copyable reply. When every recommendation
  is independently safe and complete, allow plain
  `Accept all recommendations.` and clarify that it records
  planning decisions only, not AWS access or spending.
- On a new message that may answer the pending card, parse before any project
  write and use the parser's deterministic owner-safe status. If parsing fails,
  say that nothing was recorded, state the specific invalid reply key or format,
  preserve the unchanged questions, and show the valid reply form; do not
  narrate internal IDs or hashes or echo secret-like input. If parsing succeeds, acknowledge that one answer and let the Engine project the next card.
- After the normalized write and Engine revalidation, render Answer
  Confirmation only when the caller supplies the matching new owner-response
  identity from that turn. Show "Recorded", "Project effect", and
  "Correct it"; never replay the confirmation on resume and never persist a
  shown flag.
- At Gate A, accept a correction only as
  "Change the requirements: <correction>." At Gate B, accept one only as
  "Change the design: <correction>." Parse before writing, record owner
  provenance, apply existing staleness rules, and never treat a correction as
  approval.
- The `Accept all recommendations.` payload is available only after the current
  card is presented and only when the current question is a decision with a complete
  recommendation that requires no detail. A factual question, missing
  recommendation, required detail, stale card, or altered phrase makes it unavailable.
- “Explain this question” or the legacy “Explain these questions” is a clarification, not learning mode. Explain each
  pending choice directly, state `Project state changed: No.`, rerun the Engine,
  and restore the same pending decision through the side-question presenter.

## Material decision card

Before an exact Gate A, Gate B, AWS read-only preflight, deployment, or teardown
receipt, give one short decision card with exactly these labels:

- `Decision:` what the owner is deciding now;
- `Recommendation:` Codex's evidence-backed recommendation;
- `Why:` the material requirement and evidence basis;
- `Tradeoff:` the principal benefit and cost or limitation;
- `Reply:` the exact copyable response; and
- `After that:` the work Fastlane will continue automatically.

The card summarizes but never replaces or alters the exact formal receipt.
Do not add it to routine status, side-question restoration, or an internal
checkpoint. Keep methodology and context-management terms out of the card.
## Owner Decision Briefs

Before a Gate A or Gate B receipt, render the matching
`owner_decision_brief` from the current Engine JSON. Never improvise or retain
a second editable brief.

- Gate A explains the outcome, users, first-release journey and boundary,
  success, data and access, resilience, Region and cost, assumptions, risks,
  change lineage, approval effect, and what remains unauthorized.
- Gate B starts with a one-minute executive decision, then groups every
  consequential technical decision by application/runtime, identity, data,
  messaging, edge/networking, observability, deployment/recovery, and
  validation/construction. It ends with repository-relative source locations.
- Render each claim with its exact maturity in plain language. Planned work and
  unobserved deployment never appear as proven.
- A missing, duplicate, orphaned, conflicting, stale, unsafe, or unresolved
  supporting record blocks the brief. Do not catch the diagnostic as prose or
  bypass it.
- The exact approval receipt remains last and byte-identical. Receipt-only
  owner approval remains valid; after acceptance, continue in the same run and
  show the next project section.
