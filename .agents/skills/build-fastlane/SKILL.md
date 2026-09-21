---
name: build-fastlane
description: Route approved Fastlane task execution through the existing coordinator. Use only when explicitly invoked by a compatibility workflow.
---

# Build Fastlane Compatibility Alias

Continue through `$fastlane` in the same coordinator and preserve the user's TASK-10, BUILD-10, BUILD-20,
resume, checkpoint, or release-readiness intent. Do not run a separate writer
or bypass the Fastlane Engine, Gate B, task readiness, write boundaries, attempts,
validation, or evidence rules. AWS operations require the owner's explicit
invocation of `operate-fastlane-aws` and the Engine's current phase-specific
authority; this alias never supplies either.
