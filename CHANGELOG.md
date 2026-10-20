# Changelog

All notable changes are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/).

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
