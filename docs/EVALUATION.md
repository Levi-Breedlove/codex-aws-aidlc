# Optional Fastlane Evaluations

These reviews are opt-in and run outside ordinary credential-free CI. They
validate exported evidence contracts; neither scorer invokes a model, accesses
AWS, reads credentials, or proves facts that were not actually observed.

## Model role-play evaluation

Print the scenarios and anchored `1`, `3`, and `5` rubrics for all nine criteria:

```text
python scripts/model_roleplay_eval.py plan --json
```

Use only synthetic project facts. Run every scenario at least three times and
store the complete evidence bundle outside the repository. The schema-4
evaluation manifest binds the expected commit and prompt-contract digest, then
references one transcript and separate rater scorecard files for each scenario
and iteration.

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

Score the untracked schema-4 bundle:

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

### Schema 3 migration

Schema 3 inline `live_model_observed` booleans, nested score objects, and
unresolved digest strings cannot establish file provenance and are rejected.
Do not auto-convert them. Re-export each transcript, scorecard, and required
adjudication as a schema-4 evidence bundle, calculate the actual file digests,
and rerun the scorer with the exact tested commit and prompt-contract digest.

## Disposable AWS canary evidence

The three field canaries are defined in [AWS-CANARY.md](AWS-CANARY.md). Planning
and verification remain local:

```text
python scripts/aws_canary_eval.py plan --json
python scripts/aws_canary_eval.py score --input <results.json> --bundle-root <evidence-bundle> --json
```

The verifier requires a contained, non-symlink evidence bundle whose manifest
binds Gate A, Gate B, AWS-20, teardown authority, CloudTrail export, IaC plan or
change set, smoke tests, rollback, teardown, and billing reports by SHA-256.
`CANARY_EVIDENCE_CONTRACT_PASS` proves only exported evidence integrity and
internal consistency, not AWS truth. A real canary still requires exact
owner-authorized deployment and separate teardown authority.
