# Testing

## Commands

Run from the repository root with Python 3.11 or newer:

```powershell
python -m unittest discover -s tests -v
python -m compileall -q monitor toolbox server.py tests
node --check dashboard\app.js
git diff --check
```

The CI workflow runs the unit tests on Python 3.11 and 3.13, compiles all
Python packages, checks JavaScript syntax, and runs `git diff --check`.

## Coverage

- configuration parsing and rejection paths;
- check-runner normalization, timeouts, and controlled HTTP/TLS boundaries;
- server health, status, history, and security headers;
- tool input validation, CIDR/IP/hash/HMAC behavior, request limits, malformed
  JSON, unsupported content types, and browser-local JSON enforcement;
- UI contract checks for API references, accessibility hooks, escaping, and
  responsive/reduced-motion styles.

Tests use local ephemeral servers and standard-library tooling. They must not
depend on public internet availability for the normal suite.

## Manual acceptance

For a server/API change, start a fresh instance on a non-conflicting port:

```powershell
python server.py --port 8091 --data-dir data\test-acceptance
```

Verify `/api/health`, `/api/status`, `/api/tools`, `/api/tools/run`, the static
page, and an error response. For UI changes, check desktop and mobile widths,
keyboard tab operation, form validation, empty/error output, and horizontal
overflow. Stop the temporary process when finished and do not disturb an
existing service on port 8080.

## Known limits

- Public TLS/HTTP/ICMP behavior depends on the host network. A sandbox can
  legitimately block ICMP, proxy TLS, or block a port, so those failures are
  recorded rather than treated as product success.
- Docker build verification requires a running Docker daemon.
- The current UI has no automated browser screenshot or layout assertion; a
  manual inspection is still required for visual changes.
- No automated test proves that a network target is authorized. That remains a
  human deployment responsibility.
