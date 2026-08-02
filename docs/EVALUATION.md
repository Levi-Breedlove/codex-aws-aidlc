# Optional Fastlane Evaluations

These reviews are opt-in and run outside ordinary credential-free CI. The
scorer validates exported evidence contracts; it does not invoke a model,
access AWS, read credentials, or prove facts that were not actually observed.

## Deterministic workflow corpus

`tests/test_product_journeys.py` is the credential-free Golden Project Corpus.
It exercises extracted-template setup, resume, both gates, AWS Core evidence
routing, bounded delivery, side questions, deployment/teardown separation, and
failure recovery through the real scripts. It is the mandatory deterministic
workflow baseline; model role plays and adopter pilots supplement it.

## Customer-record readability qualification

Evaluate rendered Markdown, not only raw source. A visible line is a nonblank
rendered line outside a closed `<details>` body; its `<summary>` counts once.
The six project records must open with current values, one owner need or
`Nothing`, the next Codex action, the approval/authority boundary, and useful
navigation. Exact records remain canonical below that surface.

The final customer-record correction requires all of these conditions:

- Product Agreement appears within the first 45 visible PRD lines.
- TASKS exposes active progress within 35 visible lines.
- VERIFY exposes populated claims within 30 visible lines.
- RUNBOOK exposes the operational path within 45 visible lines.
- Gate A's visible decision surface is at most 80 lines.
- Gate B's visible executive decision and technical index are at most 140 lines.
- Visible PRD, TASKS, VERIFY, and RUNBOOK lines fall at least 35 percent from
  `2fc50a22f893dce92bc996fe05fe2a57b9d65d71`, and their combined text falls by
  at least 20,000 characters.
- Disclosures are balanced and labeled. Current actions, material risks,
  authorization boundaries, commands, diagrams, and formal receipts stay open.
- Owner-visible paths contain no digest, parser, schema, routing, EARS, QAS,
  Harness, or context-management instructions.

## Model role-play evaluation

Print the scenarios and anchored `1`, `3`, and `5` rubrics for all nine criteria:

```text
python scripts/model_roleplay_eval.py plan --json
```

Use only synthetic project facts. Run every scenario at least three times and
store the complete evidence bundle outside the repository. The schema-5
evaluation manifest binds the expected commit and prompt-contract digest, then
references one transcript and separate rater scorecard files for each scenario
and iteration. Its required set adds one-question intake, Answer Confirmation,
Gate A and Gate B comprehension, source navigation, project-diagram
understanding, gate correction, exact resume, and agent-owned correction.

- `DEVELOPMENT` may use one pseudonymous rater, but can never claim release
  readiness.
- `RELEASE` requires two independent pseudonymous raters for every scenario and
  iteration.
- Every rater must score `authorization_integrity` exactly `5`.
- A difference above one point on any criterion requires an adjudication artifact
  with a non-personal rationale reference.
- Transcript, scorecard, and adjudication artifacts repeat the run's scenario,
  iteration, commit, prompt digest, and model reference. Scorecards also bind the
  transcript digest; adjudications bind every current scorecard digest.
- Every referenced artifact must be a unique, contained, regular, non-symlink
  file whose bytes match the manifest SHA-256.
- Only schemas, plans, digests, and non-personal references belong in tracked
  release evidence.

Score the untracked schema-5 bundle:

```text
python scripts/model_roleplay_eval.py score \
  --input <evidence-directory>/evaluation-manifest.json \
  --bundle-root <evidence-directory> \
  --expected-commit <40-character-commit-sha> \
  --expected-prompt-contract-sha256 <sha256:digest> \
  --json
```

The scorer validates path containment, symlink exclusion, file digests, run
bindings, rater independence, anchored scores, required adjudication, no
reported violation, no credential inspection, and no AWS account access. It
does not invoke or observe a model.

Passing statuses are deliberately narrow:

- `DEVELOPMENT_EVALUATION_EVIDENCE_CONTRACT_PASS`
- `RELEASE_EVALUATION_EVIDENCE_CONTRACT_PASS`

They mean exported evidence integrity and score consistency only. They do not
independently prove that a live model produced the transcript, determine
release readiness, or authorize publication. Ordinary CI tests only the
schema, bundle validator, and claim boundary.

The scorer derives owner turns, assistant turns, stops, automatic continuations,
and repeated owner actions from each bound transcript. It reports timing or token
totals only when every turn in that transcript contains the corresponding metric.
A repeated owner action fails the evidence contract; missing timing or token data
is simply omitted rather than invented.

## Maintainer adopter-pilot metrics

Before a release-readiness claim, maintainers may run synthetic or personal-project
pilots and retain only non-sensitive aggregate process metrics: prerequisite retries,
clarification rounds before Gate A, requirement revisions, Gate A-to-Gate B time,
architecture candidates, stale-gate events, autonomous task completions, validation
retries, and owner actions after Gate B. Ask whether the owner understood the next
action, both gates, AWS-access state, and the recommendation basis. Do not retain full
transcripts by default; tracked files may contain only a non-personal reference and
digest. Pilot metrics are evidence, never a gate or publication authority.

### Schema 4 and earlier migration

Schema 4 bundles cover the previous scenario set; schema 3 inline attestations
do not establish file provenance. Neither can be auto-converted into missing
Fastlane 1.1 observations. Rerun every schema-5 scenario and export fresh
transcripts, scorecards, and required adjudications with actual file digests,
the exact tested commit, and the current prompt-contract digest.

## AWS Core field qualification

Field qualification is a maintainer-only release activity. Require it before
the first claim of real AWS deployment readiness and repeat it after material
changes to AWS execution authority, exact receipts, AWS Core execution lanes,
optional hooks, rollback, teardown, or evidence reconciliation.

Codex selects the smallest disposable non-production scenario that exercises
the changed execution path using current AWS Core guidance, then performs and
evaluates it. Fastlane governs it through the existing Gate A, Gate B,
AWS-10, AWS-20, AWS-30, AWS-40, and AWS-50 contracts. Exercise every execution
lane claimed as supported, including `STRUCTURED_API` and `REVIEWED_SCRIPT` when
applicable.

Keep the complete evidence bundle outside the reusable template. Tracked files
may contain only non-secret references and digests. Reasoning and procedure
selection alone are not operational evidence. Field qualification is not part
of customer setup and introduces no scorer, lifecycle stage, gate, or routine
owner action.
