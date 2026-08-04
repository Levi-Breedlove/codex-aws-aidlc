# Application source

Fastlane reserves `app/**` as the single application-code root for a new
application. Codex uses it only after Gate B records the project's application
source disposition and approves the matching construction boundary.

- New application: build application code under `app/`.
- Existing application: preserve the exact source root recorded during
  brownfield design; do not create a parallel `app/` tree.
- Infrastructure-only project: record that application source is not
  applicable and leave this directory as documentation only.

Do not introduce parallel top-level `apps/` or `src/` application roots. The
canonical decision and its tradeoff live in `docs/project/PRD.md`; this file is
orientation, not approval or authority.
