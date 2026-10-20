# Changelog

All notable changes are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/).

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
