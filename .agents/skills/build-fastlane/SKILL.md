---
name: build-fastlane
description: Delegate approved Fastlane task execution. Use only when explicitly invoked by a compatibility workflow.
---

# Build Fastlane Compatibility Alias

Delegate to `$fastlane` and preserve the user's TASK-10, BUILD-10, BUILD-20,
resume, checkpoint, or release-readiness intent. Do not run a separate writer
or bypass the Fastlane Engine, Gate B, task readiness, write boundaries, attempts,
validation, or evidence rules. Route AWS mutation through AWS-10/AWS-20.
