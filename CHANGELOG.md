# Changelog

All notable changes are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/).

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
