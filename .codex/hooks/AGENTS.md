# Fastlane hook implementation guide

This guide narrows the root rules and never widens approval or authorization.

The optional hook pack is a fail-closed adapter over current Fastlane Engine
output. It never parses owner receipts independently, creates canonical state,
changes lifecycle state, or converts a native permission prompt into approval.

## Event invariants

- `SessionStart` clears private transition state and obtains fresh read-only
  Engine output.
- `PreToolUse` compares attributable tool inputs with current write and external
  authority projections. A pass means no hook denial, never automatic allow.
- `PermissionRequest` binds the normalized tool name and canonical request
  digest to its preceding session/turn request without assuming a `tool_use_id`.
- `PostToolUse` requires the exact observed `tool_use_id` and may return bounded
  corrective context; it never writes evidence.
- `Stop` continues only when the Engine permits continuation, no owner action
  is required, and no formal receipt is pending.

## Boundary handling

- File writes remain inside the repository, current Gate B write roots,
  exclusions, protected paths, and active task write set.
- Structured GitHub writes must expose the repository and target branch. Deny
  opaque shell publication and connector operations whose target cannot be
  bound safely.
- AWS requests use only the Engine's normalized
  `external_authority.request_match`. Classify capability from observable
  arguments, not advertised tool names or descriptions.
- `STRUCTURED_API`, `REVIEWED_SCRIPT`, task polling, and presigned URL requests
  must expose every field needed to prove current scope. Opaque, stale,
  wrong-kind, symlinked, or teardown-conflicting requests are denied.
- Native Codex permission and sandbox controls remain active, and IAM remains
  downstream enforcement.

## Private transition state

During one AWS mutation transition, schema 2 stores hashes only in the operating
system temporary directory. It contains no raw session, turn, tool, prompt, or
credential values; expires after 15 minutes; and is cleared on session start,
completion, malformed or legacy state, mismatch, or replay.

The handler never reads transcripts, logs prompts or tool inputs, inspects
credentials or private trust state, persists secrets, accesses AWS, or writes
project lifecycle state. Preserve these properties in focused hook tests.
