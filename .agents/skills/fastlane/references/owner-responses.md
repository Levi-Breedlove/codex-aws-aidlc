# Owner responses

- Lead with plain-language project status, not internal execution narration.
- Render routine status with `python scripts/fastlane_presenter.py owner
  --input-stdin`; do not hand-compose lifecycle routing.
- Immediately after successful initialization, render the first Engine report
  once with `python scripts/fastlane_presenter.py project-ready --input-stdin`.
- After current Gate B, render `architecture-board-offer` only with an eligible handoff and exact skill receipt; normal `owner` resume never repeats it, setup, the welcome, project settings, or Project Ready.
- Present one concrete next action. Show an owner action only for a genuine
  decision, setup step, approval, authorization, protected-boundary decision,
  or human safety review. Otherwise continue the selected phase.
- For an explicitly supplied product brief, render the Engine's
  `SOURCE_ASSISTED_DEFINE` projection with the deterministic `source-brief`
  presenter mode. Explain that the brief can reduce consultation questions but
  cannot replace the canonical PRD or import approval or authority. Keep A, B,
  and C choices separated by blank lines and accept the owner's meaning in
  ordinary language; do not require an internal reply token or numeric prefix.
- Do not expose hashes, file counts, prompt IDs, or exhaustive receipts in
  routine conversation.
- Never accept self-asserted audit prose. After observable current AWS Core
  `search_documentation` and matching `retrieve_skill` evidence, let the
  presenter name the returned skill identifier and official references, then
  state that no AWS account was accessed. If those calls are unavailable or
  unobservable, omit `Audit:` rather than claiming AWS Core use. Persist no raw
  skill content, transcript, credential, session identifier, or machine detail.
- An owner's statement that a test, preflight, deployment, recovery, or teardown
  completed is not observed evidence. Only current Engine-projected evidence may
  establish completion. Otherwise identify the statement as the owner's report,
  preserve the current evidence state, and keep the corresponding action gated.
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

## Technical consultant behavior

Owner responses provide decision support, not a raw relay of Engine fields.
For every owner-facing question, clarification, approval, or technical
recommendation:

1. Begin with the practical project consequence.
2. State what Fastlane already knows from current canonical state.
3. Identify the one decision that belongs to the owner.
4. Recommend one option only when current evidence justifies it.
5. Tie the recommendation to the approved outcome, constraints, risks,
   repository facts, or current source evidence.
6. State the principal tradeoff or limitation.
7. Explain technical terms after their plain-language meaning.
8. Explain how the answer changes requirements, design, cost, risk,
   validation, or operations.
9. Distinguish confirmed facts, repository observations, source-verified
   guidance, local evidence, AWS evidence, plans, and unauthorized actions.
10. End with exactly one current valid owner action.

Do not merely repeat Engine field names or ask the owner to choose an
implementation detail Codex can safely resolve from approved requirements and
current evidence. If no recommendation is justified, say so plainly. Critical
status, Gate, evidence, remediation, and authority facts come from the current
Engine projection and presenter; natural explanation may clarify but never
alter them.

## Plain-language decisions
For guided intake, render only the current Engine-validated
`INTAKE-CARD-*`. Keep its stable reply key for internal parser binding, but
present uppercase A/B/C decision choices, required-detail prompts, and natural
factual replies without that numeric prefix. Do not expose its internal ID,
revision, digest, or legacy reply token. The parser receives the exact card
identity separately before any write; retain `R-*` only as an internal 1.0.x
compatibility input for that same current card. Factual questions remain short
free text. Use `next_question_guidance` to render `Why this matters`, the
current question, and `What your answer changes` without repeating a generic
script. Never ask the
owner to choose project mode, delivery profile, effective risk, AWS lane, or a
combined Fastlane configuration; those are Codex-owned classifications from
confirmed facts. Recommend a choice
only when current evidence justifies it; there is no universal default. If no
recommendation is justified, render exactly
`No recommendation—choose the option that matches your situation.` followed
by `Reply with one of:` and valid examples such as `A`, `B: <required detail>`,
and `C: <required detail>`. Separate every labeled choice and reply example
with a blank line. Never label an unresolved placeholder as a copyable reply.
Rendering a card with `turn_boundary_required` ends the assistant turn; only a
new owner message may resolve it.

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
- End input requests with one short copyable reply only when that text is a
  valid current-card answer. Otherwise state one valid reply form or show
  valid option examples. A factual response may be ordinary prose without its
  internal numeric reply key; preserve punctuation such as semicolons as part
  of that one answer. A decision may use `A`, `B: <required detail>`, or
  `C: <required detail>`. Legacy keyed forms remain accepted but are not the
  preferred owner-facing format. When every recommendation
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
  shown flag. If the same response also renders the next route, use presenter
  mode `answer-progress`; its `Updated:` line is derived from the recorded
  change and must not say `Nothing.`
- At Gate A, accept a correction only as
  "Change the requirements: <correction>." At Gate B, accept one only as
  "Change the design: <correction>." Parse before writing, record owner
  provenance, apply existing staleness rules, and never treat a correction as
  approval. If a purported design correction adds a product capability, actor,
  data type, retention rule, integration, or journey absent from the current
  requirements, treat it as a requirements conflict: do not preserve Gate A,
  do not write it as design-only state, and route through the requirements
  correction path.
- The `Accept all recommendations.` payload is available only after the current
  card is presented and only when the current question is a decision with a complete
  recommendation that requires no detail. A factual question, missing
  recommendation, required detail, stale card, or altered phrase makes it unavailable.
- “Explain this question” or the legacy “Explain these questions” is a clarification, not learning mode. Explain each
  pending choice directly, state `Project state changed: No.`, rerun the Engine,
  and restore the same pending decision through the side-question presenter.

## Material decision card

Before an exact Gate A or Gate B receipt, or before an AWS read-only preflight,
deployment, or teardown receipt template, give one short decision card with
exactly these labels:

- `Decision:` what the owner is deciding now;
- `Recommendation:` Codex's evidence-backed recommendation;
- `Why:` the material requirement and evidence basis;
- `Tradeoff:` the principal benefit and cost or limitation;
- `Reply:` for a gate, the exact copyable response; for AWS, an instruction to
  fill every `<...>` placeholder and return the entire canonical block; and
- `After that:` the work Fastlane will continue automatically.

The card summarizes but never replaces or alters the exact gate receipt or the
full canonical AWS template. A placeholder-bearing AWS block is a template, not
an exact or current receipt, a copyable reply, or authority. Show the entire
applicable template after the card with its field names and order unchanged.
The human owner must fill every placeholder and return the entire block. Only
after deterministic validation against current project state may the completed
owner reply be described as the exact current receipt. Until then, authority
for that AWS action is `NONE`. Do not add the card to routine status,
side-question restoration, or an internal checkpoint. Keep methodology and
context-management terms out of the card.
## Owner Decision Briefs

Before a Gate A or Gate B receipt, render the matching
`owner_decision_brief` from the current Engine JSON. Never improvise or retain
a second editable brief.

- Gate A explains the outcome, users, first-release journey and boundary,
  success, data and access, resilience, Region and cost, assumptions, risks,
  change lineage, every owner decision and source, approval effect, correction
  syntax, what remains unauthorized, and what happens after approval.
- Gate B starts with a one-minute executive decision, then groups every
  consequential technical decision by application/runtime, identity, data,
  messaging, edge/networking, observability, deployment/recovery, and
  validation/construction. Every decision states its owner effect, selection,
  requirement basis, rationale, rejected alternatives, tradeoffs, risks and
  safeguards, evidence maturity, reconsideration trigger, and exact source.
- Put repository-relative Markdown links before the formal receipt. Receipt-only
  approval remains receipt-only; the next automatic post-approval status links
  back to the approved Gate and forward to the next canonical work section.
- Render each claim with its exact maturity in plain language. Planned work and
  unobserved deployment never appear as proven.
- A missing, duplicate, orphaned, conflicting, stale, unsafe, or unresolved
  supporting record blocks the brief. Do not catch the diagnostic as prose or
  bypass it.
- The exact approval receipt remains last and byte-identical. Receipt-only
  owner approval remains valid; after acceptance, continue in the same run and
  show the next project section.

## Comprehension, navigation, and completion replies

- A Gate-comprehension question is a side question, not approval. For Gate A,
  summarize the actual current outcome, users, first-release scope/non-goals,
  journey, and measurable success from the Engine-projected brief before
  explaining the authority limit. For Gate B, name the actual selected architecture
  and principal rejected alternative, then state the exact
  allowed local write set, command boundary, attempt/checkpoint limits, and
  exclusions from the current construction envelope. Restore the same pending
  gate action and never repeat the formal receipt.
- A source-navigation reply uses only the current Engine-projected
  `source_locators`. Render a scannable list containing each locator key,
  repository-relative path, bound heading, and inclusive current line range.
  Never reuse offsets from a different raw, template, or previously rendered
  PRD, and never estimate line numbers.
- After DIAGRAM-10, claim completion only from observed current task evidence.
  Use presenter mode `architecture-board-completion` with the current request
  packet and an Engine-captured completion projection bound to the current
  Gate B, design digest, construction authorization, and every required output
  and QA-tile byte. Fastlane independently checks the current report and
  request binding, Mermaid and source-model direction, SVG and Draw.io
  structure, artifact hashes, PNG structure, exact PNG-to-tile crops, and
  receipt file bindings. The pinned skill report may record all 20 external
  checks, including SVG-to-PNG reproduction, but Fastlane does not rerender the
  SVG or authenticate that validator execution. Treat the icon package as
  declared input; byte binding does not authenticate official provenance.
  Never describe the 20 reported checks or icon provenance as independently
  observed. Name the exact
  `dist/architecture/<DES>-<semantic-sha256>/` output root, link
  `architecture-board-task-manifest.json`, and name the current validation,
  render, and visual-review receipts. If any artifact or receipt is absent, say
  the board remains incomplete. Planned diagrams never imply implementation or
  AWS authority.
- An agent-owned correction update names the observed defect, current task and
  write boundary, and exact validation commands/evidence destinations being
  rerun, followed by the exact one-time Engine rerun command and current
  remediation fingerprint. Do not reduce it to a generic statement that
  validation failed.
