# Odświeżanie profilu systemu (cron / systemd)

Profil sprzętu i narzędzi jest używany przez czat RAG w Repo Opowieść.

## Ręcznie

```bash
cd /mnt/ollama/projekty/repo-story
bash scripts/collect-system-profile.sh > data/system-profile.json
curl -X POST http://127.0.0.1:9743/api/system-profile/upload \
  -H "Content-Type: application/json" \
  -d @data/system-profile.json
```

Lub w UI: zakładka **Diagnostyka** → **Zbierz profil systemu**.

## Cron (co 6 godzin)

```cron
0 */6 * * * cd /mnt/ollama/projekty/repo-story && bash scripts/collect-system-profile.sh > data/system-profile.json && curl -sf -X POST http://127.0.0.1:9743/api/system-profile/refresh
```

## Systemd user timer

Plik `~/.config/systemd/user/repo-story-profile.service`:

```ini
[Unit]
Description=Refresh Repo Story system profile

[Service]
Type=oneshot
WorkingDirectory=/mnt/ollama/projekty/repo-story
ExecStart=/usr/bin/curl -sf -X POST http://127.0.0.1:9743/api/system-profile/refresh
```

Plik `~/.config/systemd/user/repo-story-profile.timer`:

```ini
[Unit]
Description=Refresh system profile every 6 hours

[Timer]
OnBootSec=5min
OnUnitActiveSec=6h

[Install]
WantedBy=timers.target
```

Aktywacja:

```bash
systemctl --user daemon-reload
systemctl --user enable --now repo-story-profile.timer
```
