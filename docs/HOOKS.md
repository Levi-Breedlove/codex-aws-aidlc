# Optional Fastlane hooks

Fastlane works without repository hooks. The reviewed example is opt-in,
post-Gate-B defense in depth, and never becomes an authorization source.

## Lifecycle activation boundary

Enable this pack only after a current Gate B approves local construction. Do
not enable it during `BOOT-00`, `INTAKE-10`, `REQ-10`, or `DESIGN-10`. Before
Gate B, Fastlane intentionally has no construction write authority, so an
early-enabled pack fails closed rather than creating a new write path.

If Gate B later becomes stale or invalid, the pack fails closed. Disable it by
removing the local `.codex/hooks.json`, complete the required requirements and
design work, approve a new current Gate B, then regenerate the pack with
`configure-hooks --root . --replace` and restart Codex. Hook state or prior trust
never carries construction or AWS authority across a stale gate.

## Enable manually

1. Review `.codex/hooks.fastlane.example.json` and
   `.codex/hooks/fastlane_hook.py`.
2. After a current Gate B, ask Codex to run the setup assistant's
   `configure-hooks --root .` command with the current absolute trusted Python
   interpreter. The checked-in example has deliberately empty command fields,
   so copying it cannot run the hook and is not an activation method. Use
   `--replace` only to intentionally refresh an existing local configuration.
   If the active interpreter is inside this checkout (for example `.venv`),
   choose an installed Python outside it and run one of these equivalent forms:

   ```text
   /absolute/path/to/python scripts/setup_assistant.py configure-hooks --root .
   "C:\absolute\path\to\python.exe" scripts\setup_assistant.py configure-hooks --root .
   ```

3. Restart Codex and review the native `/hooks` trust prompt.
4. Keep trust in the adopter's local Codex profile. `.codex/hooks.json` is
   ignored and must not be committed. It contains the local absolute Python
   path generated for this checkout, never a portable project fact.

Remove the generated `.codex/hooks.json` to disable the pack.

The generated launcher binds one absolute Python executable outside the
repository and current working directory. It then walks upward from the Codex
session working directory and runs only when exactly one ancestor contains
both the Fastlane manifest and Engine. It does not invoke Git to discover the
root, and a missing or ambiguous root fails closed.

## Bounded behavior

| Event | Behavior |
|---|---|
| `SessionStart` | Clears private transition state, then runs the Fastlane Engine read-only. Untouched-template handling is defensive if the pack was enabled too early; normal activation remains post-Gate-B. |
| `PreToolUse` | Uses the Engine's current write and external-authority projections to deny only clearly out-of-bound requests. |
| `PermissionRequest` | Binds the request to its preceding event without assuming a `tool_use_id`; never auto-allows escalation and otherwise preserves normal owner approval. |
| `PostToolUse` | Runs the smallest relevant validation and returns bounded corrective context without creating evidence. |
| `Stop` | Continues only when the Engine permits automatic continuation, no owner action is required, and no formal receipt is pending. |

AWS documentation tools remain available without account access or mutation
authority. Authenticated AWS preflight tools require the exact current
`AUTHORIZE AWS READ-ONLY PREFLIGHT` receipt and may perform only its named reads
against its named identity and boundary. The Engine projects this bounded scope
as `AWS_READ_ONLY`; the receipt never authorizes mutation. Fast Dev mutations
must fit a current Gate B `MUTATE_LISTED_RESOURCES` envelope and follow an
observed ready preflight. Explicit-gate mutations additionally require current
exact AWS-20 authority, and teardown requires its distinct receipt. The handler
consumes only the Engine's derived, normalized
`external_authority.request_match`; it never reparses a receipt.

The example matches generic `aws___*` and `mcp__server__tool` families.
Fastlane classifies an AWS request by observable capability, not by advertising
one account-operation tool name. A discrete `STRUCTURED_API`
request must expose service, operation, parameters, context, and resources that
fit current authority. A `REVIEWED_SCRIPT` workflow must expose the exact
approved script bytes or a contained,
regular, non-symlink artifact whose SHA-256 matches its current `AWS-EXEC-*`
contract. Opaque, unbound, stale, wrong-kind, and teardown-conflicting account
scripts are denied. A description never proves script content.

Task polling requires an exact task identifier already present in the Engine's
derived authority; otherwise the optional adapter denies it. Presigned URL
requests must expose the S3 object, upload/download direction, positive
expiration, and matching profile when present. Their operation, resource, and
expiration must remain inside current authority.

File writes must remain inside the repository, current Gate B write roots,
exclusions and protected paths, and the active task write set. The handler
examines attributable tool fields and recognizable shell, PowerShell, MCP, and
local-function inputs. It does not silently rewrite commands.

GitHub writes must use a structured connector request whose repository and
applicable target branch match the current construction envelope. Shell-based
Git or GitHub publication is denied because the optional adapter cannot prove
its exact repository and branch. Current merge, auto-merge, workflow-rerun,
release-update, and release-upload connector calls do not expose enough trusted
target metadata, so the optional adapter denies them even when Gate B permits
merge; normal Codex approval and sandbox controls remain available with the
optional hook disabled. A future observation-bound flow may close this gap
without weakening target binding.

## Native event boundary

For `Bash` and `apply_patch`, Codex supplies the command or patch in
`tool_input.command`. MCP and local-function hooks receive that tool's argument
object. `PreToolUse` and `PostToolUse` bind the documented session, turn, and
`tool_use_id`; `PermissionRequest` binds the documented session and turn plus
the normalized tool name, canonical request digest, and current Fastlane
authority. `PostToolUse` still requires the exact observed `tool_use_id`.
Matching hooks from multiple sources can run concurrently, so review every
source displayed by native `/hooks`; the owner keeps trust outside the
repository.

During one AWS mutation transition, internal schema 2 stores only hashes under
the OS temporary directory. It contains no raw session, turn, or tool
identifiers, expires after 15 minutes, and is cleared on session start, terminal
completion, malformed or legacy state, mismatch, or replay. The record is never
packaged, authoritative, or a substitute for native approval.

A request that passes these advisory comparisons receives no hook denial, not
an automatic allow. Native Codex approval and sandbox controls remain active,
and IAM determines whether an AWS request can execute.

The handler does not read transcripts, log prompts or tool inputs, inspect
credentials or private trust state, persist secrets, change lifecycle state, or
access AWS.

## Authority boundary

Hooks are defense in depth. A hook allow or lack of denial is not Gate A, Gate
B, GitHub authority, AWS authority, or teardown authority. Codex sandbox and
owner approvals still apply. Permission requests are never auto-allowed, and
any concurrent deny remains effective. See the current
[Codex hooks documentation](https://learn.chatgpt.com/docs/hooks).
