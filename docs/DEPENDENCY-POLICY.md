# Dependency Policy

Fastlane uses the current official AWS Core plugin from the AWS Agent Toolkit:

```text
Marketplace: aws/agent-toolkit-for-aws
Plugin: aws-core@agent-toolkit-for-aws
Policy: OFFICIAL_CURRENT_NO_TEMPLATE_PIN
```

The template does not redistribute AWS Core and does not pin its version or
commit. Plugin installation, updates, and native hook trust stay in each
adopter's local Codex profile and are never written to the repository.

## When AWS Core is required

Fresh templates require current official AWS Core before initialization.
Initialized projects skip the prerequisite gate during ordinary resume. During
Define, query AWS Core only when a current AWS fact materially affects
feasibility; current attributable evidence is required for the evidence-bound
AWS work at DESIGN-10 and AWS-10.

Use it for current service behavior, Region support, IAM, networking,
encryption, quotas, reliability, observability, pricing drivers, deployment,
rollback, operations, and teardown. When unavailable, pause only the affected
AWS-specific step and provide one concise owner action.

## Evidence

Installation metadata is not design evidence. DESIGN-10 and AWS-10 require
fresh attributable `search_documentation` followed by matching
`retrieve_skill` results from the official identity. Record the observed
current version as metadata, not a
pin. Generic connectors, cached prose, and model memory do not satisfy required
evidence.

## Authority and privacy

AWS Core is an advisor. It cannot approve Gate A, Gate B, or an AWS mutation.
Tool availability never grants AWS authority. Prerequisite checks do not
persist plugin state, trust state, usernames, client paths, credentials,
account identifiers, or local setup history. Later gated and AWS operations
intentionally retain the minimum audit metadata required by the approved
Fastlane evidence contracts; protect those records before publication.

## Deterministic Python quality checks

Fastlane fixes Ruff at `0.16.0` for repository lint and formatting checks. The
configuration selects only `E4`, `E7`, `E9`, and `F`, so a future change to
Ruff's defaults cannot silently expand the Fastlane contract. Markdown is
excluded because Fastlane's contract documents are governed by their own
integrity validators rather than a Python formatter.

CI runs read-only Ruff lint and format checks over `bootstrap.py`, `scripts`,
`tests`, and `.codex/hooks`. The Ruff action is pinned to an immutable commit.
Ruff checks Fastlane's Python; it does not replace AWS Core, access an AWS
account, or change Fastlane's product, architecture, gate, or authority model.

## GitHub Actions monitoring

Dependabot checks only GitHub Actions dependencies each week and targets
`fast-lane-maint`. Its proposals require human review; Fastlane configures no
automatic merge, custom registry, credential, or write token.

GitHub security updates target the repository default branch when
`target-branch` is configured. If the default branch ever differs from
`fast-lane-maint`, maintainers must explicitly reconcile urgent security pin
updates into the customer branch. Dependabot proposals never replace the
required cross-platform validation, immutable action pin, or publication
authority.
