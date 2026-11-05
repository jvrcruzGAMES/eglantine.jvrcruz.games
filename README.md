# Eglantine nx2 build distribution

A local build worker watches `https://github.com/Djihads80/Eglantine`, branch `nx2`, every two minutes. It also rebuilds unchanged source every hour (configurable with `REBUILD_SECONDS=3600`), measured from the start of the last successful build. Builds never overlap; when a build takes over an hour, the next hourly build runs after it finishes and the next poll. It compiles Linux x86_64 and cross-compiles Windows x86_64 with MinGW using MXE. Only a complete set of packages is published. A failure leaves the previous release available and retries after 30 minutes. No GitHub credentials or upstream changes are needed.

## Run

Requires Linux, Python 3.11+, Docker, Git, GnuPG, `apt-ftparchive` (Ubuntu package `apt-utils`), and systemd user services. Docker must be available to your user.

```sh
cp .env.example .env    # optional: adjust the public URL or polling interval
./install.sh
loginctl enable-linger "$USER"
```

The site listens on **0.0.0.0:39402**. The installer enables `eglantine-web.service` and `eglantine-worker.service` for the current user. Linger keeps them running after logout and starts them at boot. Builds are capped at 6 CPUs and 10 GiB RAM. The first Windows toolchain build can take hours and substantial disk space; subsequent builds reuse it and ccache. Ubuntu 24.04 is the Linux ABI baseline.

```sh
systemctl --user status eglantine-web eglantine-worker
journalctl --user -u eglantine-worker -f
curl http://127.0.0.1:39402/api/status
systemctl --user stop eglantine-worker
# Stop any active owned build container when stopping manually:
docker stop eglantine-build-linux eglantine-build-windows
```

The web page shows build state, the active build log, the last successful commit, checksums, and source downloads. Download buttons remain unavailable until the first complete release. Runtime data stays in ignored `data/`.

## Server deployment with nginx and system services

Place this repository at `/opt/apps/eglantine.jvrcruz.games`. The system units in `deploy/` run as `apps`: `eglantine-web` serves the website and `eglantine-worker` watches and builds the upstream branch. These replace the user-service installation above on the server and start automatically at boot without a login session.

Install the prerequisites above, nginx, and Docker on the server, then run:

```sh
cd /opt/apps/eglantine.jvrcruz.games
# Create the service account only if it does not already exist.
id apps >/dev/null 2>&1 || sudo useradd --system --user-group --home-dir /opt/apps/eglantine.jvrcruz.games --no-create-home --shell /usr/sbin/nologin apps
sudo usermod -aG docker apps
sudo chown -R apps:apps /opt/apps/eglantine.jvrcruz.games
sudo install -m 0644 deploy/eglantine-web.service deploy/eglantine-worker.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now docker eglantine-web eglantine-worker

sudo install -m 0644 deploy/nginx.conf /etc/nginx/sites-available/eglantine.jvrcruz.games
sudo ln -sfn /etc/nginx/sites-available/eglantine.jvrcruz.games /etc/nginx/sites-enabled/eglantine.jvrcruz.games
sudo nginx -t
sudo systemctl reload nginx
```

The Docker group must exist (created by the Docker installation). If `apps` already exists with a different primary group, use that group in the ownership command. The web service binds to `127.0.0.1:39402` by default; `.env` can override `BIND` and `PORT`, so retain those values to match nginx. Avoid running the user services and system services on the same machine at the same time.

`deploy/nginx.conf` accepts HTTP on port 80 for `eglantine.jvrcruz.games` and streams requests to `127.0.0.1:39402`, including package range downloads and update metadata. Configure HTTPS separately at the origin or through your Cloudflare Tunnel; this config does not contain certificates. For Cloudflare Full (strict) with a direct origin connection, add an HTTPS listener and a valid origin certificate before enabling that mode.

```sh
sudo systemctl status eglantine-web eglantine-worker
sudo journalctl -u eglantine-worker -f
curl -H 'Host: eglantine.jvrcruz.games' http://127.0.0.1/healthz
# After pulling updated service definitions, reinstall them and daemon-reload.
sudo systemctl restart eglantine-web eglantine-worker
```

## Public domain

Hosting is prepared locally; Cloudflare DNS and routing will be configured separately. For Cloudflare Tunnel, point the public hostname to `http://localhost:39402`; the local service does not terminate TLS. A tunnel does not need inbound port forwarding. `deploy/cloudflared.example.yml` contains a ready-to-adapt ingress rule; for an existing tunnel, add only that hostname rule before its catch-all. Disable caching for `/api/status`, `/apt/*`, and `/updates/*`; do not cache stale update metadata. Preserve HTTP Range headers and 206 responses.

Create DNS records for `eglantine.jvrcruz.games` pointing to this server, then proxy HTTPS to `127.0.0.1:39402`. An example is in `deploy/Caddyfile`. If the server is behind NAT, forward ports 80/443 to your reverse proxy. Set `PUBLIC_URL` before building: it is embedded in the AppImage metadata and the Debian update source. Changing it requires rebuilding packages.

## Downloads and updates

- `/updates/Eglantine-x86_64.AppImage`: stable AppImage download.
- `/updates/Eglantine-x86_64.AppImage.zsync`: AppImageUpdate delta feed; embedded using `zsync|https://eglantine.jvrcruz.games/updates/Eglantine-x86_64.AppImage.zsync`.
- `/apt`: signed APT repository, suite `stable`, component `main`, architecture `amd64`.
- `/eglantine-archive-keyring.gpg`: public archive key.
- `/api/status`: watcher and release metadata.
- `/releases/<version>/`: immutable artifact URLs (see the release metadata; no directory listing).

Install the downloaded Debian package with `sudo apt install ./eglantine_amd64.deb`. It installs `/usr/bin/eglantine`, a bundled application under `/opt/eglantine`, an application launcher and icon, the archive key, and `/etc/apt/sources.list.d/eglantine.list`. Updates use normal `apt update` and `apt upgrade`. AppImage updates use AppImageUpdate; the emulator's own upstream update checker is disabled. Windows ZIP updates are manual.

APT metadata is signed with the locally generated archive key. **Back up `data/gnupg/` securely** and retain it across redeployments; losing it breaks trust for existing installations. Never publish that directory. Only the public key is mounted into the build container. Only the latest successful release is retained. After the complete replacement is signed and atomically published, older release directories (including their AppImages, ZIPs, sources, Debian packages and APT indexes) and abandoned staging artifacts are deleted. Failed builds preserve the current release. APT indexes contain only the latest Debian package. Clients using an old release URL or APT index during the switch may need to refresh and retry. Build logs and compiler/toolchain caches are retained.

## Builds

`builder/linux.sh` follows upstream's CMake and linuxdeploy approach, using Qt 6.8.3 on Ubuntu 24.04. The `.deb` wraps the same bundled AppDir, so it does not depend on the distribution's older Qt. `builder/windows.sh` builds a pinned MXE toolchain with shared Qt 6 Widgets and Charts, Boost, FFmpeg and other dependencies, then recursively bundles DLL dependencies and Qt plugins into the ZIP. Neither build enables PGO. Toolchain source pinning is in the Windows script; linuxdeploy's continuous tools and upstream dependencies may need maintenance over time.

Publication stages the files, generates hashes and APT metadata, signs the repository, then atomically switches `data/public/current`. The HTTP server supports byte ranges for delta downloads and does not expose private state or directory listings. The source archive contains the application checkout, fetched application dependencies, and builder scripts; toolchain caches are kept separately.

## Validation

```sh
python3 -m unittest discover -s tests -v
python3 -m compileall -q service builder/windows_deps.py
bash -n builder/*.sh install.sh
node --check web/app.js
```

Integration tests generate two signed test repositories and verify signatures, removal of superseded packages, atomic publication, failed-release preservation, HTTP ranges, HEAD requests and path traversal rejection. They use temporary data and do not publish test artifacts to the running site.
