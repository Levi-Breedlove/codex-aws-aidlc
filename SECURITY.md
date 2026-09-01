# Security Policy

## Supported state

Fastlane 1.3.4 is maintained on the protected customer branch `fast-lane`. The
protected `fast-lane-foundation` branch preserves the 1.0.5 predecessor and
remains outside the customer release flow. A published release identifies the
exact template revision it contains.

## Report a concern

Use GitHub private vulnerability reporting when available. Otherwise contact
the repository owner privately. Never include credentials, customer data,
production identifiers, secret values, or active tokens.

Include the affected version or commit, observable behavior, a minimal
synthetic reproduction, and the safeguard that should have held.

## Trust boundaries

Fastlane gates govern workflow; they are not IAM, account, network, or runtime
security boundaries. Codex permissions, AWS Core availability, credentials,
prior access, or a passing check never authorize AWS activity.

Fastlane uses current official `aws-core@agent-toolkit-for-aws` as an AWS
research advisor. The template does not pin the plugin, redistribute it, read
its private local state, or manage its hooks. Codex's native plugin and hook
controls remain owner-managed. Fastlane requires attributable current evidence
for material AWS design and execution planning, but does not add a separate
owner trust gate.

AWS Core may expose authenticated operations. Their presence grants no
authority to invoke them.

## Optional hook guardrails

Fastlane does not install or enable repository hooks by default. The reviewed
example in `.codex/hooks.fastlane.example.json` is opt-in. After a current
Gate B, the owner reviews the example and handler, asks Codex to run
`python scripts/setup_assistant.py configure-hooks --root .` with a trusted
Python interpreter, restarts Codex, and reviews the native `/hooks` trust
prompt. The generated `.codex/hooks.json` is ignored; copying the example does
not activate the pack.

The handler does not read transcripts, log prompts or tool inputs, persist
trust or secrets, inspect credentials, or access AWS. It consumes the Fastlane Engine's
normalized `external_authority.request_match` projection and never parses raw
receipts independently. Structured AWS requests are checked only against
observable exact fields. A multi-step account script requires exact reviewed
bytes or a contained immutable artifact with the current approved digest;
opaque or unbound scripts are denied rather than inferred from prose.

The handler never auto-allows an approval request. It binds `PermissionRequest`
to the preceding event with hashed session/turn values, normalized tool name,
canonical request digest, and current authority; only `PreToolUse` and
`PostToolUse` require `tool_use_id`. One private schema-2 transition record may
exist under the OS temporary directory for at most 15 minutes. It stores hashes,
not raw identifiers, and clears on session start, terminal completion, malformed
or legacy state, mismatch, or replay. It is never packaged or authoritative.

Hook denials and continuation checks are defense in depth. Engine-projected
write and external authority are derived views of existing records; they grant
nothing. Lack of a hook denial is not Gate A, Gate B, GitHub, AWS, or teardown
authority and does not replace native owner approval, the Codex sandbox, IAM,
or observed AWS evidence. Review all active hook sources in `/hooks` because
Codex can run matching hooks from more than one configuration layer.

## Setup controls

- After fresh-template prerequisites pass, BOOT-00 asks only for project name,
  preferred Region, and budget posture.
- Fresh templates require current official AWS Core before initialization.
  Initialized projects skip the prerequisite gate during ordinary resume;
  missing material evidence pauses only the affected AWS-specific step.
- Installation commands are owner-run; Fastlane never installs software,
  changes plugin state, signs in, or trusts hooks.
- Only the official Agent Toolkit source is accepted for required AWS evidence.
- Setup never inspects credentials, accesses an AWS account, or calls AWS
  account tools.
- Login, plugin, hook, machine, username, credential, and session state are
  never written into tracked files or release archives.

## Project and AWS controls

Generated projects should prove:

- approved access succeeds and unapproved access is denied;
- secrets stay out of code, logs, fixtures, evidence, and release artifacts;
- invalid or oversized input is rejected at the boundary;
- IAM permits only required actions on required resources;
- sensitive data uses approved encryption and retention;
- failures are safe and telemetry is observable;
- DESIGN-10 records current AWS Core evidence for consequential architecture,
  IAM, Region, security, reliability, cost, and quota decisions;
- AWS-10 first records current documentation guidance without account access,
  then requires the exact owner-approved read scope before authenticated
  preflight, and records observed readiness before any mutation authorization;
  and
- deployment and teardown stay inside the named account, Region, environment,
  resources, operations, finite cost ceiling, rollback plan, and expiration.

Use no AWS identity for documentation discovery. Use only the exact approved
read-only identity for authenticated preflight. When mutation is separately
approved, prefer a short-lived role scoped to that exact authorization. The
read-only receipt, Gate A, and Gate B do not substitute for mutation authority.

Do not hide a discovered defect. Record it in `docs/project/BUGFIX.md` or an
authorized private issue while keeping sensitive evidence private.
