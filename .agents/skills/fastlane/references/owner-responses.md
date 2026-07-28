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
- Answer side questions directly, state whether project state changed, and
  restore the pending next action with `python scripts/fastlane_presenter.py
  side-question --input-stdin` after rerunning the doctor.
- A side question never repeats a formal Gate A, Gate B, or AWS receipt. It
  restores the current deterministic next action, including an existing owner
  approval when one is pending.
- A pre-Gate-A AWS example must say:
  `Illustrative architecture candidate — not selected or approved.`
- Use `explain-fastlane` only for an explicit explanation request.

## Plain-language decisions

- Explain the real-world consequence before a technical name or abbreviation.
  Keep precise engineering terms in canonical records, but do not require the
  owner to know them.
- Unless the owner already used the term or asks for technical detail, translate
  `RTO` into how quickly service returns after an outage, `RPO` into how much
  recent data might need recovery, `p95` into “at least 95 out of every 100
  requests,” concurrency into people using the product at the same time, and
  metadata into concrete examples such as hidden location and device details.
- Present at most three numbered decisions. For each, mark one `Recommended`
  choice, state its principal benefit or limitation, and offer no more than two
  understandable alternatives.
- End input requests with one short copyable reply. When every recommendation
  is independently safe and complete, allow `Accept all recommendations.` and
  clarify that it records planning decisions only, not AWS access or spending.
- “Explain these questions” is a clarification, not learning mode. Explain each
  pending choice directly, state `Project state changed: No.`, rerun the doctor,
  and restore the same pending decision through the side-question presenter.

## Material decision card

Before an exact Gate A, Gate B, AWS deployment, or teardown receipt, give one
short decision card with exactly these labels:

- `Decision:` what the owner is deciding now;
- `Recommendation:` Codex's evidence-backed recommendation;
- `Why:` the material requirement and evidence basis;
- `Tradeoff:` the principal benefit and cost or limitation;
- `Reply:` the exact copyable response; and
- `After that:` the work Fastlane will continue automatically.

The card summarizes but never replaces or alters the exact formal receipt.
Do not add it to routine status, side-question restoration, or an internal
checkpoint. Keep methodology and context-management terms out of the card.
