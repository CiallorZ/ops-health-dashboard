# Roadmap

This roadmap is intentionally staged. A phase is complete only when its
acceptance criteria have executable tests and observed verification. Features
are not promised dates; the order can change when a real defect or safety issue
has higher priority.

## Principles

- Local-first, zero runtime dependencies, no telemetry.
- One coherent product surface rather than a collection of unrelated demos.
- Every tool has bounded input, clear errors, deterministic tests, and a
  documented trust boundary.
- Prefer useful, reviewable iterations over contribution-graph activity.

## v0.2.0 - Toolbox foundation

Status: implemented in the current release candidate.

- [x] Unified tool registry, metadata, input validation, and normalized errors.
- [x] CIDR/IP analysis and hash/HMAC tools.
- [x] Browser-local JSON formatting.
- [x] Responsive toolbox UI and API contract tests.
- [ ] Verify candidate release in a clean container build on a host with Docker.

Acceptance: all automated tests pass on Python 3.11/3.13; API/UI paths are
verified on a fresh local server; no outbound tool requests are made.

## v0.3.0 - Diagnostics and reports

- Add read-only local network diagnostics with explicit targets and bounded
  timeouts.
- Add DNS lookup and route/interface summaries without changing system
  configuration.
- Add an exportable, self-contained diagnostic report that labels measured
  facts, skipped checks, and unavailable capabilities.
- Add test doubles so normal tests never require the public internet.

Acceptance: a failed/blocked operation is distinguishable from a successful
negative result; reports contain no secrets and render correctly offline.

## v0.4.0 - Monitoring continuity

- Add per-check retry policy, grouped assets, and retry/backoff visibility.
- Add daily aggregation and a compact availability/expiry timeline.
- Add optional webhook notifications with deduplication and cooldown.

Acceptance: duplicate alerts are suppressed, delivery failures are logged
without secrets, and retry/aggregation behavior is covered by controlled tests.

## v0.5.0 - Windows and automation

- Add read-only Windows system/disk/process/network summaries.
- Add a controlled scheduled-task view and exportable run history.
- Publish a documented deployment and backup story.

Acceptance: privileged operations are opt-in, no shell interpolation of
untrusted input is introduced, and autostart/update behavior is exercised on a
real Windows environment.

## Later candidates

- Text diff, regex tester, encoding conversion, timestamp conversion.
- TLS configuration review with safe, non-intrusive probes.
- Dependency vulnerability checks with an explicitly pinned toolchain.
- Read-only sharing behind an authenticated reverse proxy.

These are candidates, not commitments. Each requires a security review and a
clear user need before implementation.
