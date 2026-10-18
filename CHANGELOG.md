# Changelog

All notable changes are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/).

## [0.2.0] - 2026-10-18

### Added

- `GET /api/report` downloads a self-contained HTML snapshot for local,
  offline review. The report separates measured results, disabled checks, and
  unmeasured capability limits.

### Security

- Report exports HTML-escape untrusted values and remove URL userinfo, query
  parameters, and fragments before rendering.
