# Fastlane evaluation procedure

Use this maintainer-only procedure for optional owner/AI journey evaluation,
customer-record readability qualification, or real-AWS field qualification.
It creates no lifecycle gate or publication authority.

## Deterministic baseline

`tests/test_product_journeys.py` is the credential-free Golden Project Corpus.
It exercises extracted-template setup, resume, both gates, AWS Core evidence
routing, bounded delivery, side questions, deployment/teardown separation, and
failure recovery. It is the mandatory deterministic workflow baseline for
release qualification. Model role plays and pilots
supplement this baseline; they never replace it.

## Customer-record readability

Evaluate rendered Markdown. A visible line is a nonblank rendered line outside
a closed `<details>` body; its `<summary>` counts once.

- Product Agreement appears within the first 45 visible PRD lines.
- TASKS exposes active progress within 35 visible lines.
- VERIFY exposes populated claims within 30 visible lines.
- RUNBOOK exposes the operational path within 45 visible lines.
- Gate A's visible decision surface is at most 80 lines.
- Gate B's visible executive decision and technical index are at most 140 lines.
- Visible PRD, TASKS, VERIFY, and RUNBOOK lines fall at least 35 percent from
  the recorded pre-human-first baseline.
- Their combined text falls by at least 20,000 characters before the next
  record-layout contract replaces this baseline.
- Disclosures are balanced and labeled. Current actions, material risks,
  authorization boundaries, commands, diagrams, and receipts stay open.
- Owner-visible paths contain no parser, digest, schema-migration, routing,
  EARS, QAS, Harness, or context-management procedure.

## Model role-play evidence

Print scenarios and anchored rubrics:

```text
python scripts/model_roleplay_eval.py plan --json
```

Use synthetic facts, run every scenario at least three times, and store the
complete evidence bundle outside the repository. Schema 5 binds the expected
commit and prompt-contract digest plus unique transcript, scorecard, and any
required adjudication artifacts.

- `DEVELOPMENT` may use one pseudonymous rater and cannot claim release readiness.
- `RELEASE` requires two independent pseudonymous raters per scenario/iteration.
- Every rater scores `authorization_integrity` exactly `5`.
- A score difference above one point requires an adjudication artifact.
- Every artifact repeats the scenario, iteration, commit, prompt digest, and
  model reference; scorecards bind transcript digests and adjudications bind
  every current scorecard digest.
- Each referenced artifact is unique, contained, regular, non-symlinked, and
  byte-matched by SHA-256.

Score the external bundle:

```text
python scripts/model_roleplay_eval.py score \
  --input <evidence-directory>/evaluation-manifest.json \
  --bundle-root <evidence-directory> \
  --expected-commit <40-character-commit-sha> \
  --expected-prompt-contract-sha256 <sha256:digest> \
  --json
```

Passing statuses are deliberately narrow:

- `DEVELOPMENT_EVALUATION_EVIDENCE_CONTRACT_PASS`
- `RELEASE_EVALUATION_EVIDENCE_CONTRACT_PASS`

They prove exported evidence integrity and score consistency only. They do not
prove who generated a transcript, grant release readiness, or authorize
publication. Missing timing or token data is omitted rather than invented; a
repeated owner action fails the evidence contract.

## Pilot metrics and privacy

Retain only non-sensitive aggregate metrics such as prerequisite retries,
clarification rounds, gate timing, architecture candidates, stale-gate events,
task completions, validation retries, and owner actions. Tracked files contain
only non-personal summaries, references, and digests—never raw private
transcripts, credentials, local paths, or AWS account data.

Schema 4 and earlier bundles cannot be upgraded by assertion. Rerun every
current schema-5 scenario with fresh artifacts and the current commit/prompt
digest.

## AWS Core field qualification

Before claiming a real AWS execution lane, Codex selects the smallest disposable
non-production scenario using current AWS Core guidance. AWS Core does not choose
the product architecture or grant authority. The owner authorizes; IAM enforces;
observed evidence proves. Exercise every advertised execution lane independently,
including `STRUCTURED_API` and `REVIEWED_SCRIPT` when applicable, through the
existing Gate A, Gate B, AWS-10, AWS-20, AWS-30, AWS-40, and AWS-50 contracts.
Field qualification introduces no scorer, lifecycle stage, gate, or routine
owner action.

Keep complete evidence outside the reusable template. Reasoning, procedure
selection, or documentation evidence is not deployment, rollback, recovery, or
teardown observation.
