# Optional Fastlane hooks

Fastlane works without repository hooks. The reviewed example is opt-in,
defense in depth, and never becomes an authorization source.

## Enable manually

1. Review `.codex/hooks.fastlane.example.json` and
   `.codex/hooks/fastlane_hook.py`.
2. Copy the example to `.codex/hooks.json` only after review:

   ```bash
   cp .codex/hooks.fastlane.example.json .codex/hooks.json
   ```

   ```powershell
   Copy-Item .codex/hooks.fastlane.example.json .codex/hooks.json
   ```

3. Restart Codex and review the native `/hooks` trust prompt.
4. Keep trust in the adopter's local Codex profile. `.codex/hooks.json` is
   ignored and must not be committed.

Remove the copied `.codex/hooks.json` to disable the pack.

## Bounded behavior

| Event | Behavior |
|---|---|
| `SessionStart` | Runs the doctor read-only; an untouched template gets prerequisite context, while an initialized project gets short current-state context. |
| `PreToolUse` | Uses the doctor's current write and external-authority projections to deny only clearly out-of-bound requests. |
| `PermissionRequest` | Never auto-allows escalation; otherwise preserves the normal owner approval flow. |
| `PostToolUse` | Runs the smallest relevant validation and returns bounded corrective context without creating evidence. |
| `Stop` | Continues only when the doctor permits automatic continuation, no owner action is required, and no formal receipt is pending. |

AWS documentation tools remain available without mutation authority. Read-only
AWS tools require the existing read-authority contract. Fast Dev mutations must
fit a current Gate B `MUTATE_LISTED_RESOURCES` envelope. Explicit-gate
mutations must match current exact AWS-20 authority, and teardown must match a
distinct teardown receipt. The handler consumes only the doctor's derived,
normalized `external_authority.request_match`; it never reparses a receipt.

The example recognizes official local names such as `aws___call_aws` and
`aws___run_script`, plus ordinary `mcp__server__tool` names. A structured API
request is compared using observable service, operation, parameters, Region or
profile, resources, artifact, and plan fields. A reviewed script must expose
the exact approved script bytes or a contained, regular, non-symlink artifact
whose SHA-256 matches its current `AWS-EXEC-*` contract. Opaque, unbound, stale,
wrong-kind, and teardown-conflicting account scripts are denied. A description
never proves script content.

File writes must remain inside the repository, current Gate B write roots,
exclusions and protected paths, and the active task write set. The handler
examines attributable tool fields and recognizable shell, PowerShell, MCP, and
`run_script` inputs. It does not silently rewrite commands.

## Native event boundary

For `Bash` and `apply_patch`, Codex supplies the command or patch in
`tool_input.command`. MCP and local-function hooks receive that tool's argument
object. Matching hooks from multiple sources can run concurrently, so review
every source displayed by native `/hooks`; the owner keeps trust outside the
repository.

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
