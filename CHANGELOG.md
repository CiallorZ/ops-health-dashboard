# Changelog

All notable changes are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Fixed

- Normal shutdown keeps the data-directory lock until active sampling and
  HTTP handlers finish; idle HTTP connections have a 10-second timeout.
- Dashboard clears stale summary values on connection failure and offers a
  domain filter based on the actual checks in the latest snapshot.
- `/readyz` now tests directory writes and access to an existing history file;
  storage failures return 503 without exposing filesystem error details.

## [0.13.0] - 2026-10-27

### Fixed

- Acquire the data-directory lock before initializing history and alert stores;
  retain the lock file after release to prevent concurrent processes from
  locking different files during a handover.

### Added

- Declarative per-check `assertions`: each rule targets one probe metric or
  `latency_ms`, accepts bounded `warn` / `fail` thresholds, and defaults to no
  behavior change when omitted. Operators choose the expected comparison; the
  default probe thresholds remain evidence for the legacy verdict.
- Bounded assertion grammar: `== != > >= < <= in exists missing`, at most 8
  rules per check, 16 `in` values, finite numbers/booleans and literal or
  prefix strings only. Regex, expression engines and cross-check math are
  deliberately unsupported.
- Structured assertion evidence (`actual`, verdict and judgment reason) in
  snapshots, per-run history and per-check heartbeats. `unknown` is used for
  a missing metric or incompatible metric type; it is never counted as
  available and is not retried.
- Dashboard and offline reports expose assertion evidence and truthful
  `unknown` totals/health. Long trends distinguish an unknown day from a
  healthy day and render missing availability as `--`.

## [0.12.0] - 2026-10-26

### Added

- `PROBES` registry in `monitor/checks.py`: each probe declares `validate()`
  and `run()`, and `run_check` dispatches through the registry instead of the
  type `if/elif` chain. Existing four probe behaviors and messages are
  unchanged; a contract test pins the registry to `SUPPORTED_TYPES` in
  `monitor/config.py` so the two can never drift.
- Probe declarations now carry `domain`, `kind` (`prober` / `reader`) and
  `requires_secret`. A probe declared as a reader must set
  `requires_secret=True`; invalid declarations fail at import time instead of
  silently mislabelling metrics.
- `domain` dimension on every check: optional `domain` config field (validated
  against the seven planned domains), default `network` so existing configs
  keep working, and the value flows into config output, results, snapshot,
  per-run history, transition events, alert payloads, offline report and
  Prometheus `domain` label.
- Per-domain concurrency budgets via `domain_budget` (1–8 workers per domain,
  default 4). Each domain runs in its own thread pool so a slow domain cannot
  starve a fast one; results keep the configured check order.
- `domain_budget` is exposed by `/api/config` and the dashboard policy panel
  shows the default budget and how many domains override it.

### Changed

- The Prometheus `domain` label now reports the real monitoring domain instead
  of the free-text business `group`. Metric names and label sets are
  unchanged; only the value changes.

## [0.11.1] - 2026-10-24

### Fixed

- Windows single-instance lock actually enforced: `msvcrt.locking` now locks
  byte 0 (`seek(0)` first). Previously the lock landed at EOF, so two
  processes could hold different bytes and run concurrently against the same
  data directory.
- Windows `release()` unlocks byte 0; previously the mismatched offset raised
  `PermissionError` and left the lock handle open until process exit.
- Lock files are only removed while this process still provably owns them
  (POSIX: content verified under the held `flock`; Windows: owner PID
  content verified after the handle closes). A lock file taken over by
  another holder is never deleted, closing the release/unlink race where a
  third process could acquire a lock file name the real owner still holds.

### Added

- `tests/test_instance_lock.py`: first real unit tests for the instance lock
  (the v0.11.0 changelog claimed these existed; they did not). Covers
  second-instance rejection with owner PID, release cleanup and reacquire,
  foreign/taken-over lock file preservation, flock mutual exclusion, and the
  release-without-acquire no-op. POSIX paths run on CI (ubuntu); Windows
  paths run locally and were verified with real two-process races.

## [0.11.0] - 2026-10-21

### Added
- Single-instance lock for the data directory (`.sentinel.lock`): POSIX `flock`
  / Windows `msvcrt` / `O_EXCL` fallback; a second process fails fast with
  stderr message and exit code 3 without writing history.
- `GET /healthz` (process liveness, no sampling) and `GET /readyz` (config
  loaded, data directory writable, scheduler running; `503` with reasons when
  not ready).
- `GET /metrics` in Prometheus text format; labels restricted to
  `domain` / `id` / `status`; only reports the latest cached snapshot and never
  triggers a new check run.
- Unit tests for the instance lock, `/healthz`, `/readyz`, `/metrics`, label
  contract, and cached/uncached metrics payloads.
- `deploy/systemd/sentinel.service` sample with `Restart=on-failure` and
  `ProtectSystem=strict`.

### Fixed
- Lock acquisition failure now propagates to `main()` so the process exits with
  code 3 instead of returning a bare integer from `build_server()`.

## [0.10.0] - 2026-10-21

### Added

- Planned maintenance windows: `maintenance_windows` in `checks.json`
  declares a bounded list (max 20, max 30 days each) of time-boxed windows
  that can target specific checks or every check.
- While a window is active, sampling and dashboard state keep working exactly
  as before; only Webhook delivery is suppressed, and the alert ledger stores
  the window name as the suppression reason.
- `GET /api/maintenance` and `automation.maintenance` in `/api/status` report
  active windows, upcoming windows, covered check ids, and how many checks
  currently have alerting suppressed.
- The dashboard gained a maintenance panel showing active/upcoming windows,
  their scope, remaining time and whether alerting is suppressed.

### Security

- Window timestamps must carry an explicit timezone offset; naive datetimes
  are rejected instead of being silently interpreted in local time.
- `check_ids` referencing an unknown check fails configuration loading, so a
  typo cannot silently disable nothing.
- Suppressing an alert during maintenance does not start a cooldown, so the
  first real transition after the window still gets delivered.

## [0.9.0] - 2026-10-21

### Added

- `history.jsonl` now has hard on-disk bounds: a 4 MiB current file, two
  rotated archives, and a 5000-line load ceiling. Rotation stays inside the
  data directory and always keeps the newest runs.
- `GET /api/health` and `automation.retention` in `/api/status` report the
  real footprint: current bytes, archive list, total bytes, configured caps,
  loaded lines, and whether older samples were truncated.
- The dashboard policy panel shows history usage against the cap, the number
  of archives, and an explicit "已截断" state when older samples were dropped.
- Oversized or malformed history files are compacted to their newest complete
  lines at startup instead of being trusted whole or crashing the service.

### Security

- Archive rotation resolves every path inside the configured data directory
  before deleting or replacing anything, so a crafted file name cannot reach
  outside `data/`.
- Truncation is reported as a fact rather than hidden: trends keep computing
  only from samples that still exist on disk.

## [0.8.0] - 2026-10-21

### Added

- A bounded certificate expiry calendar now derives per-check remaining days
  from the real `expires_at` returned by each TLS handshake, and exposes them
  through `GET /api/certificates`.
- The calendar grades each certificate against the configured
  `tls_warn_days` / `tls_fail_days` thresholds, counts expired / critical /
  warning / healthy certificates, and keeps at most eight entries inside the
  90-day upcoming window.
- The dashboard gained a certificate panel showing tracked certificates, the
  nearest expiry, warn/critical counts, and an upcoming list with expiry date,
  common name, and whether the chain was verified.
- `monitor/certificates.py` is covered by unit tests for grading, sorting,
  bounding, stale-value handling, missing metrics, and clamped limits.

### Security

- The certificate calendar only reports values measured by a completed TLS
  handshake; failed handshakes, non-TLS checks, and malformed metrics are
  skipped rather than filled with assumed expiry dates. The endpoint reuses
  the same-origin API and never exposes webhook URLs or signing secrets.

## [0.7.0] - 2026-10-21

### Added

- Long-term trend rollups now aggregate real UTC calendar days, expose a
  bounded 1-30 day window, and compute p50/p95 latency from fixed latency
  buckets. Missing days are never invented or backfilled.
- `GET /api/trends?days=7` returns daily availability, sample counts, latency
  percentiles, per-check rollups, and the bucket boundaries used for math.
- The dashboard now has a 7-day long-term trend panel that names the UTC day
  boundary, shows days with data, and keeps loading/error states truthful.

### Security

- Trend responses use the existing same-origin API, do not expose webhook URLs
  or secrets, and are bounded by `MAX_TREND_DAYS` / `MAX_TREND_ITEMS`.

## [0.6.0] - 2026-10-21

### Added

- A background monitor now samples configured checks without requiring an open
  browser. The interval is bounded from 10 to 3600 seconds and exposed through
  `/api/status`, `/api/health`, and the dashboard automation panel.
- Webhook alerts are sent only for real status transitions. Delivery includes
  a bounded cooldown, queue limit, timeout, optional HMAC-SHA256 signature, and
  zero to two retries.
- Alert delivery evidence is persisted in a bounded local ledger and exposed
  through `/api/alerts` and the dashboard. Webhook URLs, signing secrets, URL
  query parameters, and raw exception text are not exposed.
- The UI now shows scheduler state, last/next sample time, and recent webhook
  outcomes alongside heartbeat and Important Events data.
- A reproducible local demo now includes a webhook receiver and automatic
  background sampling.
- Versioned source packages can be built with `scripts/build-release.ps1` for
  direct download and offline installation.

### Changed

- README and the self-contained landing page now cover background monitoring,
  alert behavior, downloadable installation, Docker installation, and a
  complete local demo path.
- Configuration validation now bounds monitor names, targets, tags, webhook
  URLs, environment-variable names, and notification policy values.
- The dashboard sync interval is now 10 seconds while detection continues on
  the configured background schedule.

### Security

- Webhook secrets can be referenced through environment variables and are
  never returned by `/api/config`, `/api/alerts`, reports, or logs.
- Outbound webhook payloads redact URL userinfo, query parameters, and
  fragments from monitored targets.

## [0.5.0] - 2026-10-21

### Added

- Per-check history records now store bounded `id`, `status`, and
  `latency_ms` evidence without duplicating names, targets, URLs, or error
  details.
- The dashboard renders the last 40 heartbeats, availability, average latency,
  labels, search, and `ok` / `warn` / `fail` filtering for each check.
- `check_history` snapshots now include per-check statistics and an Important
  Events list generated only from real adjacent status changes.
- The UI and README borrow the compact monitor/heartbeat information
  architecture proven by Uptime Kuma while keeping Sentinel's Python standard
  library implementation and local-only boundary.

### Changed

- Configuration now accepts at most 200 checks so snapshots and history cannot
  grow without a fixed upper bound.
- Legacy history rows without per-check records remain readable and contribute
  no invented samples.
- Refreshed README, landing page, and desktop/mobile screenshots for v0.5.0.

## [0.4.0] - 2026-10-21

### Added

- Self-contained project landing page at `docs/index.html` with real desktop
  and mobile screenshots, ready for GitHub Pages.
- Maintainer documentation: `ROADMAP.md`, `docs/SECURITY.md`,
  `docs/TESTING.md`, `docs/RELEASE.md` and project-level `AGENTS.md`.
- Reproducible local demo (`examples/checks.demo.json` and
  `examples/demo_targets.py`) that needs no public network access.
- Offline reports now include an attempt column and label retry recovery.
- `--version` CLI flag; `User-Agent` and `Server` headers now track the
  running version.

### Fixed

- Offline report rendered integer `0` as a blank cell in the summary counts.
- `?force=1` no longer returns a cached snapshot inside the 8-second cache
  window, while concurrent refreshes still share a single run.

### Changed

- README rewritten with screenshots, quick start, configuration, API,
  architecture, security and testing sections.

## [0.3.0] - 2026-10-20

### Added

- Checks can opt into zero to two extra attempts with `retry_attempts`. The
  final result reports the actual number of attempts and whether it recovered,
  while persistent failures remain visible.

## [0.2.1] - 2026-10-18

### Added

- Checks can now declare a bounded `group` label. Snapshot results, the live
  dashboard, and offline reports retain it so operators can review related
  targets together.

## [0.2.0] - 2026-10-18

### Added

- `GET /api/report` downloads a self-contained HTML snapshot for local,
  offline review. The report separates measured results, disabled checks, and
  unmeasured capability limits.

### Security

- Report exports HTML-escape untrusted values and remove URL userinfo, query
  parameters, and fragments before rendering.
