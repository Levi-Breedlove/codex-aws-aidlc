# Optional Fastlane hooks

Fastlane works without repository hooks. The Fastlane Engine always owns
validation, routing, and derived authority. Hooks are an optional fail-closed
adapter that can surface Engine decisions closer to a Codex tool request.

```text
Engine = authority and routing
Hooks = optional defense in depth
Owner = enables and trusts hooks
```

## When to enable them

Enable this pack only after a current Gate B approves local construction. Do
not enable it during `BOOT-00`, `INTAKE-10`, `REQ-10`, or `DESIGN-10`.

If Gate B becomes stale, remove the local `.codex/hooks.json`, complete the
required requirements and design work, approve a current Gate B, regenerate
the pack, and restart Codex. Prior hook trust never carries construction or
AWS authority across a stale gate.

## Enable manually

1. Review `.codex/hooks.fastlane.example.json` and
   `.codex/hooks/fastlane_hook.py`.
2. Ask Codex to run the setup assistant with a trusted Python interpreter:

   ```text
   python scripts/setup_assistant.py configure-hooks --root .
   ```

   The checked-in example has empty command fields and cannot activate itself.
   Use `--replace` only when intentionally refreshing an existing local setup.
3. Restart Codex and review the native `/hooks` trust prompt.
4. Keep the generated `.codex/hooks.json` local. It is ignored and must not be
   committed.

Remove `.codex/hooks.json` and restart Codex to disable the pack.

## What the pack does

| Moment | Owner-visible effect |
|---|---|
| Session starts | Runs the Engine read-only and clears private temporary transition state. |
| Before a tool call | Denies only requests that are clearly outside current Engine-projected boundaries. |
| Permission is requested | Preserves normal owner approval and never auto-allows escalation. |
| After a tool call | Runs the smallest relevant validation and returns bounded corrective context. |
| Codex is about to stop | Continues only when the Engine allows it and no owner action or formal receipt is pending. |

Hooks never create evidence, approve a gate, authorize GitHub or AWS, change
project state, read transcripts, inspect credentials, or access AWS. A request
that receives no hook denial still needs native Codex approval, sandbox access,
current Fastlane authority, and—when applicable—IAM permission.

## Important limitations

- Hooks are defense in depth, not a replacement for the Engine.
- Every matching active hook source shown by `/hooks` can run; review them all.
- The adapter can deny an opaque request when it cannot prove the target and
  boundary. Disable the optional pack when a legitimate workflow cannot be
  expressed safely, then rely on the Engine and normal Codex controls.
- Hook configuration and trust are local machine state, not repository facts.

Technical native-event and temporary-state invariants are maintained in
`.codex/hooks/AGENTS.md`; owners do not need those implementation details to
use or disable the pack.

See the current [Codex hooks documentation](https://learn.chatgpt.com/docs/hooks).
