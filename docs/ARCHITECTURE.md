# Architecture

## Shape

The project is a single-process Python application with a static browser client:

- `server.py` binds the local HTTP server, routes APIs, serves files, and adds
  security headers.
- `monitor/` owns configuration, network checks, result normalization, caching,
  and JSONL history.
- `toolbox/` owns deterministic, non-monitoring tools and the registry used by
  both the catalog and execution APIs.
- `dashboard/` contains the browser UI. It has no build step and no framework.
- `tests/` uses `unittest` and controlled local servers where network behavior
  is involved.

## Request flow

1. The browser requests static assets or an API from the same origin.
2. `GET /api/status` asks `CheckRunnerService` for a snapshot. Cached snapshots
   are reused for the configured window; `force=1` starts a fresh bounded run.
3. The runner executes configured checks and stores normalized results plus a
   history summary in `data/history.jsonl`.
4. `GET /api/tools` returns registry metadata. `POST /api/tools/run` accepts a
   small JSON object, dispatches to one allow-listed handler, and returns a
   structured result or caller-safe error.
5. Browser text is escaped before HTML insertion; JSON formatting runs locally
   and never crosses the service boundary.

## Extension contract

Add a tool by creating a focused module under `toolbox/`, validating all inputs,
raising `ToolError` for caller errors, and registering a `ToolSpec` in
`toolbox/registry.py`. The metadata must state whether execution is local or
server-side. A tool must not accept arbitrary shell commands, write arbitrary
files, or contact a target unless that behavior has an explicit, reviewed
design.

Monitoring check types are configured in `checks.json` and parsed by
`monitor/config.py`. New types need a parser branch, a bounded runner
implementation, public result fields, tests, and documentation.

## Storage and compatibility

- `checks.json` is the source of truth for monitored assets and thresholds.
- `data/history.jsonl` is append-oriented local history and is not a database.
- Public APIs return JSON and keep the current field names for compatible
  MINOR releases.
- A breaking API, configuration, or result-shape change requires a MAJOR
  version and migration guidance.

## Security boundary

The server is intentionally unauthenticated and defaults to loopback. It does
not provide a safe public-internet deployment by itself. See
`docs/SECURITY.md` for the threat model and deployment constraints.
