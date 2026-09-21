---
name: launch-fastlane
description: Route Fastlane initialization or resume through the existing coordinator. Use only when explicitly invoked by a compatibility workflow.
---

# Launch Fastlane Compatibility Alias

Continue through `$fastlane` in the same coordinator and preserve the user's `init template`, initialize,
resume, or BOOT-00 intent. Do not run an independent lifecycle, repeat setup
questions, or render a second status. The `fastlane` coordinator owns routing,
writes, checkpoints, and owner conversation.
