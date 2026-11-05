#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
root=$PWD
mkdir -p "$HOME/.config/systemd/user" data
for unit in web worker windows-worker; do
 cat > "$HOME/.config/systemd/user/eglantine-$unit.service" <<UNIT
[Unit]
Description=Eglantine $unit
After=network-online.target
Wants=network-online.target
[Service]
Type=simple
WorkingDirectory=$root
Environment=PYTHONUNBUFFERED=1
EnvironmentFile=-$root/.env
ExecStart=/usr/bin/python3 $root/service/$(test "$unit" = web && echo server || echo worker).py
Restart=on-failure
RestartSec=15
TimeoutStopSec=60
[Install]
WantedBy=default.target
UNIT
 if [[ "$unit" = windows-worker ]]; then
  sed -i '/Environment=PYTHONUNBUFFERED=1/a Environment=BUILD_PLATFORM=windows' "$HOME/.config/systemd/user/eglantine-$unit.service"
  sed -i '/RestartSec=15/a ExecStopPost=-/usr/bin/docker stop -t 10 eglantine-build-windows eglantine-nightly-build-windows' "$HOME/.config/systemd/user/eglantine-$unit.service"
 fi
 if [[ "$unit" = worker ]]; then
  sed -i '/RestartSec=15/a ExecStopPost=-/usr/bin/docker stop -t 10 eglantine-build-linux eglantine-nightly-build-linux' "$HOME/.config/systemd/user/eglantine-$unit.service"
 fi
done
systemctl --user daemon-reload
systemctl --user enable --now eglantine-web.service eglantine-worker.service eglantine-windows-worker.service
