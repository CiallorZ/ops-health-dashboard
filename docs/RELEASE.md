# Release and automation

## Version gate

A release is a reviewed state of the repository, not a daily activity marker.

1. Confirm the branch and clean/understood worktree with `git status`.
2. Run every command in `docs/TESTING.md`.
3. Review `git diff`, `git diff --cached`, and the public API/UI changes.
4. Update `VERSION`, `monitor/__init__.py`, `CHANGELOG.md`, and affected docs
   together when the change is substantive.
5. Commit on a dedicated branch and open a pull request. Do not merge, tag,
   deploy, or publish without explicit approval.
6. After CI succeeds, record the commit and CI run. A tag or GitHub release is
   a separate, explicit action.

## Daily maintenance automation

The local Codex automation should run in a dedicated maintenance branch and
open/update one reviewable PR. It must not push directly to `main`, merge,
deploy, publish secrets, or create activity-only commits. Each run chooses one
bounded task from `ROADMAP.md` or a verified defect, runs the full test gate,
and reports limitations honestly.

The scheduler is local to the Codex environment. Its time zone and invocation
must be verified from the saved automation configuration; if the scheduler
cannot access the repository or credentials expire, report the blocker rather
than claiming a successful run.
