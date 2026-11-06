#!/bin/bash
# Install/update all server units together so neither platform worker is omitted.
set -euo pipefail
project=$(cd "$(dirname "$0")/.." && pwd)
if [[ $EUID -ne 0 ]]; then
 echo 'Run with sudo: sudo bash deploy/install-services.sh' >&2
 exit 1
fi
if [[ "$project" != /opt/apps/eglantine.jvrcruz.games ]]; then
 echo 'Server units require the project at /opt/apps/eglantine.jvrcruz.games' >&2
 exit 1
fi
id apps >/dev/null
for unit in web worker windows-worker; do
 install -m 0644 "$project/deploy/eglantine-$unit.service" /etc/systemd/system/
done
systemctl daemon-reload
systemctl enable eglantine-web eglantine-worker eglantine-windows-worker
systemctl restart eglantine-web eglantine-worker eglantine-windows-worker
systemctl --no-pager --full status eglantine-web eglantine-worker eglantine-windows-worker
