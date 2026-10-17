# Changelog

All notable changes are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/).

## [0.2.0] - 2026-10-17

### Added

- Extensible local toolbox registry with normalized metadata, input validation,
  caller-facing errors, and a bounded execution API.
- Browser-local JSON formatting and validation; payloads for that tool are
  deliberately rejected by the server.
- Offline CIDR calculation, IPv4/IPv6 address analysis, and SHA/MD5/HMAC
  digests.
- `GET /api/tools` catalog and `POST /api/tools/run` execution endpoint with a
  64 KiB request limit and JSON content-type enforcement.
- Responsive toolbox UI with keyboard-operable tabs, explicit loading/error
  states, and a clear local-only trust boundary.
- Unit/API/UI contract tests and stricter CI compilation coverage.

### Changed

- Service/version metadata now reports `0.2.0`.
- Docker image includes the toolbox package so the new API also works in a
  container.

### Security

- Tool inputs are type-checked and bounded; server errors do not expose
  tracebacks.
- No new runtime dependencies, telemetry, arbitrary command execution, or
  external scanning capability was introduced.

## [0.1.0] - 2026-10-17

### Added

- Initial zero-dependency health dashboard with ICMP, TCP, TLS, and HTTP
  checks, local history, CI, Windows autostart, and Docker support.
