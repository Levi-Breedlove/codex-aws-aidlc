# Fastlane dependency policy

This page tells project owners and maintainers which external tools Fastlane
expects and who is responsible for them.

**Project owners:** [AWS Core](#aws-core) · [Privacy and authority](#privacy-and-authority)

**Maintainers:** [Ruff](#ruff) · [Mermaid rendering](#mermaid-rendering) ·
[GitHub Actions](#github-actions)

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

Ruff `0.16.0` checks Fastlane’s own Python during maintainer validation.
It is pinned so a changing default cannot silently expand the repository
contract.

Fastlane adopters do **not** install Ruff system-wide to initialize or use the
template. Maintainers may run an ephemeral `uvx ruff==0.16.0` command. Ruff does
not access AWS or change Fastlane state.

## Mermaid rendering

Maintainer release qualification may use `@mermaid-js/mermaid-cli` `11.16.0`
with an exact Node.js version to parse and render the packaged diagram procedure
plus synthetic Golden Project diagrams. Fastlane adopters do not install this
renderer to use the template. Qualification produces four sanitized synthetic
PRDs, 11 deduplicated Mermaid sources, and both themes (22 SVG review artifacts)
in an explicit local evidence directory outside the reusable template. It never
reads or uploads adopter project files, machine paths, credentials, account
data, or session state. A successful render proves syntax and produces an
inspectable artifact; it does not by itself prove visual quality.

## GitHub Actions

Fastlane intentionally ships no recurring GitHub Actions workflow for pushes or
pull requests. Dependabot still checks GitHub Actions dependencies weekly
against `fast-lane`; it does not test, approve, or merge a change. Any update
requires human review and the same exact-head local release qualification as any
other maintenance change. Updates are never auto-merged, and publication
authority remains required. With no action references in the current tree, the
scan normally has nothing to update; the configuration is retained for future
GitHub Actions dependencies.

## Privacy and authority

Dependency checks do not persist usernames, client paths, credentials, AWS
account identifiers, plugin state, or hook trust. Tool availability never
creates Fastlane, GitHub, or AWS authority.
