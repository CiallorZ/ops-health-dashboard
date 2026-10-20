# Project Instructions

## Stack

- Python 3.11+ standard library only
- Vanilla HTML / CSS / JavaScript
- `unittest` for tests
- No third-party runtime dependencies

## Commands

```powershell
python server.py
python -m unittest discover -s tests -v
python -W error::ResourceWarning -m unittest discover -s tests -q
python -m compileall -q monitor toolbox server.py tests
node --check dashboard\app.js
git diff --check
```

## Layout

- `monitor/` — config, checks, runner, history, report
- `dashboard/` — page, styles, frontend logic
- `tests/` — local-only unit tests
- `examples/` — reproducible demo config and substitutes
- `docs/` — landing page and maintainer docs
- `server.py` — HTTP entry point

## Rules

- Preserve the no-fake-data rule: every status must come from a real check.
- Keep network tests local and deterministic; never require public internet.
- Bound timeouts, retries, history size and report content.
- Never expose or commit credentials, tokens, cookies or private keys.
- Keep the response security headers and path traversal protections intact.
- Update `CHANGELOG.md`, docs and version files for user-visible changes.
- Do not commit generated `data/`, `__pycache__/` or log files.
- Prefer small, reviewable changes with a single main problem per iteration.
