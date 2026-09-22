# Authorization receipts

Use the exact canonical blocks in `prompts/CODEX-PROMPTS.md` and the current
authoritative records. Do not paraphrase, reorder, complete, or self-accept a
receipt.

A placeholder-bearing block is a canonical receipt template, not an exact or
current receipt and not authority. Present the entire applicable template with
its field names and order unchanged. The human owner must fill every `<...>`
placeholder and return the entire block. Only that complete owner reply, after
deterministic validation against current project state, becomes the exact
current receipt. Until then, authority for that action is `NONE`; do not
substitute a prose checklist or perform the read, mutation, or removal.

- Gate A binds the current requirements revision, cost posture, accepted
  assumptions, and human approver.
- Gate B binds the current requirements and design revisions, construction
  authorization, canonical envelope digest, and human approver.
- AWS read-only preflight binds the current construction authorization,
  identity, account, Region, environment, artifact, resources, allowed reads,
  expiration, and human approver. It permits no mutation and precedes any
  authenticated AWS-10 account access.
- AWS deployment and teardown remain separate exact authorizations naming the
  allowed identity, target, resources, operations, finite cost ceiling,
  rollback, and validity.
- Each AWS receipt's resources and operations must be a duplicate-free,
  wildcard-free subset of the Gate B maximum and the current phase. Execution
  uses only the intersection of Gate B, phase mode, current evidence, and the
  exact phase-specific receipt; a receipt never broadens an approved
  construction envelope. For S3 operations, match the actual partition, exact
  bucket, and complete object key to the named resource; a similar name or
  prefix never supplies authority.
- The exact teardown receipt authorizes only AWS-50 mutations. Its ID and exact
  receipt digest bind the AWS-50 attempt and the subsequent AWS-40 terminal
  reconciliation row. AWS-50 always returns to AWS-40 for authenticated reads;
  no receipt, result, or postcondition permits AWS-50 to perform read-only
  reconciliation.
- Tool access, credentials, task state, silence, or continued conversation are
  never authorization.
