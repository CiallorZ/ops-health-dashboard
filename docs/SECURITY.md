# Security

## Threat model

The intended deployment is a trusted user running the dashboard on their own
Windows machine and viewing it through a local browser. The service has no user
accounts, so any process or person that can reach the listening port can read
the dashboard and invoke its allow-listed tools.

Protected assets include local configuration, the append-only history file, and
the integrity of the host. The most relevant threats are:

- exposure of a loopback-only service to a LAN or the internet;
- SSRF or unintended access to local/private services through monitoring
  targets;
- command injection or arbitrary file access through future tools;
- credential leakage through URLs, logs, history, or reports;
- malicious input causing unbounded CPU, memory, request size, or outbound
  traffic;
- supply-chain risk from unnecessary dependencies.

## Current controls

- Bind address defaults to `127.0.0.1`.
- HTTP security headers include CSP, `nosniff`, no framing, no-referrer, and
  no caching for API responses/static files.
- URL targets with embedded credentials are rejected by configuration parsing.
- Check timeouts are bounded; tool request bodies are capped at 64 KiB; hash
  input is capped at 1,000,000 characters; tool inputs are allow-listed.
- The server does not execute arbitrary commands or write arbitrary paths.
- Tool failures return sanitized messages and never include tracebacks.
- The JSON formatter runs in the browser and is rejected by the server.
- There are no runtime dependencies, telemetry, or analytics.

## Deployment rules

Do not expose the server directly to the internet. If a reverse proxy is used,
add authentication, authorization, TLS, request limits, logging, and an
explicit decision about which APIs are reachable. Docker's host mapping should
remain loopback-only unless that boundary has been reviewed.

Monitoring targets are still a user-chosen network boundary. Only configure
assets you are authorized to probe. The service can reach localhost and private
addresses; do not turn it into an open target-selection proxy.

## Secrets and evidence

Never put credentials, tokens, cookies, private keys, or sensitive query
parameters in `checks.json`, tool input, logs, history, or reports. Redact such
values before sharing diagnostics. If a secret is exposed, rotate it; removing
the file alone does not revoke it.

## Reporting a problem

For a suspected local vulnerability, preserve the minimum evidence needed to
reproduce it, avoid contacting third-party assets, and document the affected
version and configuration. Do not publish secrets or exploit details until a
fix and disclosure path are agreed.
