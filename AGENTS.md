# Agent Development Rules

This repository is a local-first operations toolbox. Keep the Python standard
library and dependency-free browser stack unless a documented architecture
decision proves that a dependency provides a clear, necessary benefit.

## Product boundaries

- Default to `127.0.0.1`; never expose the service to a LAN or the internet
  without an explicit design for authentication, authorization, and transport.
- Do not add telemetry, analytics, credential collection, or hidden outbound
  requests.
- Network checks may only contact targets explicitly configured by the user.
  Tools must not become unauthorized scanners or arbitrary command runners.
- Treat configuration, request bodies, target names, and browser-rendered
  values as untrusted. Validate inputs, apply bounded timeouts and sizes, and
  escape all remote text before inserting it into HTML.
- Never commit secrets, `.env` files, captured credentials, logs, generated
  history, or real private asset inventories.

## Change discipline

- Inspect `git status`, the relevant source, tests, and roadmap before editing.
- Make the smallest complete change. Preserve existing API contracts unless a
  versioned breaking change is explicitly approved.
- Do not use destructive Git operations or overwrite unrelated worktree changes.
- Add a focused test for every behavior change, including malformed input,
  timeout/error paths, and regressions in existing checks.
- Use semantic versioning: PATCH for compatible fixes, MINOR for compatible new
  capabilities, MAJOR for incompatible changes. Update `VERSION`,
  `monitor/__init__.py`, `CHANGELOG.md`, and user documentation together when
  the version changes.
- Do not bump a version for documentation-only or purely cosmetic changes.

## Verification gate

Run these from the repository root before committing:

```powershell
python -m unittest discover -s tests -v
python -m compileall -q monitor toolbox server.py tests
node --check dashboard\app.js
git diff --check
```

For API or UI changes, start a fresh server on a non-conflicting port and
verify real HTTP responses. For visual changes, check desktop and mobile
layouts, keyboard focus, empty/error states, and horizontal overflow.

Do not claim a test, CI run, push, PR, deployment, or automation succeeded
unless its result was observed. If a required dependency or network is
unavailable, report the limitation and leave the change uncommitted when the
quality gate cannot be met.

## Git and release flow

- Develop on a dedicated branch. Never force-push or discard user changes.
- Keep commits focused and describe the verified behavior they add.
- Push only when credentials and the intended remote are confirmed.
- Open or update a pull request for review; do not merge to `main`, tag a
  release, deploy, or publish automatically without explicit approval.
- GitHub activity is a byproduct of useful work, not a target. Empty commits,
  artificial formatting churn, and duplicate daily changes are prohibited.
