# Service Lifecycle Declaration

**Service:** svc-driftless
**State:** ACTIVE
**Owner:** @joepetjr
**Last Reviewed:** 2026-07-22
**Auto-Review Date:** 2026-10-20 (90 days from last commit)

## State Definitions

- **ACTIVE:** Under active development, receives regular updates, full CI coverage
- **MAINTENANCE:** Stable, minimal changes, security patches only, reduced CI
- **ARCHIVED:** No further development, frozen for reference, excluded from CI

## Ownership Responsibilities

- Keep this service's `README.md` and `CHANGELOG.md` in step with what has
  actually shipped. (The pre-extraction `.data/plans/…` build plan they were
  written against stayed behind in the workspace monorepo; there is no `.data/`
  in this repo, so it is no longer a reference anyone can follow.)
- Review the state declaration above at the auto-review date.
