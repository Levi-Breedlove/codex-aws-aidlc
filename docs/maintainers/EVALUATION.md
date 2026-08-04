# Fastlane evaluation

This page explains what Fastlane’s validation can and cannot prove. Detailed
maintainer procedures live in the scoped `maintain-fastlane` evaluation
reference rather than in customer documentation.

## Credential-free baseline

Fastlane’s required repository tests exercise initialization, resume, both
owner gates, AWS Core evidence routing, bounded delivery, side questions,
deployment and teardown separation, and failure recovery. Packaging checks
also extract a customer template and validate its real startup path.

These results can verify repository contracts and deterministic behavior. They
do not prove that independent adopters understand the workflow or that an AWS
deployment, rollback, recovery, or teardown succeeded in a real account.
The [Fastlane 1.2 qualification matrix](../QUALIFICATION.md) maps each promised
owner-visible journey to its executable deterministic evidence.


## Human-first record checks

Rendered project records should show current state, one owner action or
`Nothing`, Codex’s next action, the authority boundary, and useful links on
their first screen. Gate A and Gate B briefs must explain the decision,
evidence status, corrections, unauthorized work, and what happens next before
the exact receipt.

The visible targets are intentionally small:

- Product Agreement appears within 45 visible PRD lines.
- Active progress appears within 35 TASKS lines.
- Populated claims appear within 30 VERIFY lines.
- The ordinary operator path appears within 45 RUNBOOK lines.
- Gate A is at most 80 lines and Gate B is at most 140 lines.
- During the human-first transition, the four primary records shrink
  by at least 35 percent and at least 20,000 characters from the recorded
  baseline.

Machine-maintenance tables may remain in the canonical record under clearly
labeled disclosures, but they must not crowd the ordinary owner path.

## Deterministic synthetic owner-facing journeys

Maintainers may run synthetic role-play scenarios to review question pacing,
answer confirmation, gate comprehension, document navigation, resume,
side-question recovery, and Codex-owned correction. Store full evidence
outside the reusable template. Tracked results contain only sanitized,
non-personal summaries and stable references.
In the 1.2 release statement, **deterministic synthetic owner-facing journeys**
means credential-free scenarios exercised by repository tests. Optional external model
role-play remains a separate evidence class and must be reported as not run
unless its complete current evidence bundle was actually scored.


Passing an exported evidence-contract validator proves integrity of that
bundle, not that a live model produced it or that Fastlane is ready for public
release.

## Independent adopter evidence

With informed consent, maintainers may collect non-sensitive aggregate metrics
such as setup retries, clarification rounds, gate comprehension, validation
retries, autonomous task completion, and unnecessary owner interruptions.
Never commit raw private transcripts, credentials, AWS identifiers, local
paths, or personal system information.

## Real AWS field qualification

Real AWS claims require a separately authorized disposable scenario and
observed evidence for each advertised execution lane. Documentation research
and local tests are not deployment, rollback, recovery, or teardown evidence.
Field qualification is not customer setup and introduces no lifecycle gate.

Maintainers: follow
`.agents/skills/maintain-fastlane/references/evaluation.md` for the canonical
evaluation procedure, schemas, commands, evidence boundaries, and release
claim rules.
