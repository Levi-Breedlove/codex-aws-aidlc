# Fastlane dependency policy

This page tells project owners and maintainers which external tools Fastlane
expects and who is responsible for them.

## AWS Core

Fastlane uses the current official AWS Core plugin:

```text
Marketplace: aws/agent-toolkit-for-aws
Plugin: aws-core@agent-toolkit-for-aws
Policy: OFFICIAL_CURRENT_NO_TEMPLATE_PIN
```

The template does not redistribute or pin AWS Core. Installation, updates, and
native trust stay in each owner’s local Codex profile and are never written to
the project repository.

Fresh templates require current official AWS Core before initialization.
Initialized projects skip the prerequisite gate during ordinary resume. Material AWS design and operating work
requires fresh attributable `search_documentation` followed by the matching
`retrieve_skill`; cached prose, memory, installation metadata, and generic
connectors do not replace that evidence.

AWS Core is an advisor. It cannot approve a gate or authorize AWS access.

## Ruff

Ruff `0.16.0` checks Fastlane’s own Python during maintainer validation and CI.
It is pinned so a changing default cannot silently expand the repository
contract.

Fastlane adopters do **not** install Ruff system-wide to initialize or use the
template. Maintainers may run the pinned CI action or an ephemeral
`uvx ruff==0.16.0` command. Ruff does not access AWS or change Fastlane state.

## GitHub Actions

Dependabot checks GitHub Actions dependencies weekly against `fast-lane`.
Updates require human review and the full cross-platform validation suite;
they are never auto-merged. Immutable action pins and publication authority
remain required.

## Privacy and authority

Dependency checks do not persist usernames, client paths, credentials, AWS
account identifiers, plugin state, or hook trust. Tool availability never
creates Fastlane, GitHub, or AWS authority.
