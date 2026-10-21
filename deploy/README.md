# Deployment samples

## systemd

1. Copy the repository to `/opt/sentinel` (or adjust paths).
2. Create a data directory: `mkdir -p /var/lib/sentinel`.
3. Copy `deploy/systemd/sentinel.service` to `/etc/systemd/system/sentinel.service`.
4. Edit paths/ports if needed. Credentials must be provided via environment variables or
   files placed outside the repository (this service uses `ProtectSystem=strict`).
5. Run `systemctl daemon-reload && systemctl enable --now sentinel`.

Check status: `systemctl status sentinel` / `journalctl -u sentinel -n 50`.

## Windows

Use the existing helper scripts:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\install-autostart.ps1
```

Uninstall: `scripts\uninstall-autostart.ps1`. The startup entry runs `scripts\run-server.ps1`
under the current user and does not require administrator privileges.
