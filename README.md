# Eglantine nx2 build distribution

A local build worker watches `https://github.com/Djihads80/Eglantine`, branch `nx2`, every two minutes. It also rebuilds unchanged source every hour (configurable with `REBUILD_SECONDS=3600`), measured from the start of the last successful build. Builds never overlap; when a build takes over an hour, the next hourly build runs after it finishes and the next poll. It compiles Linux x86_64 and cross-compiles Windows x86_64 with MinGW using MXE. Only a complete set of packages is published. A failure leaves the previous release available and retries after 30 minutes. No GitHub credentials or upstream changes are needed.

## Run

Requires Linux, Python 3.11+, Docker, Git, GnuPG, `apt-ftparchive` (Ubuntu package `apt-utils`), and systemd user services. Docker must be available to your user.

```sh
cp .env.example .env    # optional: adjust the public URL or polling interval
./install.sh
loginctl enable-linger "$USER"
```

The site listens on **0.0.0.0:39402**. The installer enables `eglantine-web.service` and `eglantine-worker.service` for the current user. Linger keeps them running after logout and starts them at boot. Build containers have no Docker CPU quota. Compiler parallelism defaults to at most six jobs, clamped to the Docker daemon CPU count. Memory defaults to min(10 GiB, 75% of Docker host RAM). `BUILD_JOBS` and `BUILD_MEMORY` can override these settings. The first Windows toolchain build can take hours and substantial disk space; subsequent builds reuse it and ccache. Ubuntu 24.04 is the Linux ABI baseline.

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

```

The Docker group must exist (created by the Docker installation). If `apps` already exists with a different primary group, use that group in the ownership command. The web service binds to `127.0.0.1:39402` by default; `.env` can override `BIND` and `PORT`, so retain those values to match nginx. Avoid running the user services and system services on the same machine at the same time.

### HTTPS with nginx and Let's Encrypt

`deploy/nginx.conf` redirects HTTP to HTTPS and proxies HTTPS to `127.0.0.1:39402`. It uses `/etc/letsencrypt/live/eglantine.jvrcruz.games/fullchain.pem` and `privkey.pem`. Obtain the certificate before installing this config. The HTTP challenge path stays available for renewals. References: [nginx HTTPS](https://nginx.org/en/docs/http/configuring_https_servers.html), [Certbot webroot](https://eff-certbot.readthedocs.io/en/stable/using.html#webroot).

Point DNS at this server and allow inbound ports 80 and 443. HTTP-01 validation must reach this nginx server on port 80; Cloudflare redirects or cache rules must not intercept `/.well-known/acme-challenge/*`. For a Cloudflare Tunnel directly to the app, retain the existing ingress configuration and Cloudflare edge HTTPS.

On Ubuntu/Debian, bootstrap with HTTP, issue the certificate, then switch to HTTPS:

```sh
cd /opt/apps/eglantine.jvrcruz.games
sudo apt-get install -y certbot
sudo install -d -m 0755 /var/www/letsencrypt
sudo install -m 0644 deploy/nginx-http.conf /etc/nginx/sites-available/eglantine.jvrcruz.games
sudo ln -sfn /etc/nginx/sites-available/eglantine.jvrcruz.games /etc/nginx/sites-enabled/eglantine.jvrcruz.games
sudo nginx -t && sudo systemctl reload nginx
sudo certbot certonly --webroot -w /var/www/letsencrypt --cert-name eglantine.jvrcruz.games -d eglantine.jvrcruz.games
# Continue only after Certbot successfully issues the certificate.
sudo install -m 0644 deploy/nginx.conf /etc/nginx/sites-available/eglantine.jvrcruz.games
sudo nginx -t && sudo systemctl reload nginx
sudo install -D -m 0755 deploy/renewal-reload-nginx.sh /etc/letsencrypt/renewal-hooks/deploy/eglantine-reload-nginx
sudo systemctl enable --now certbot.timer
sudo certbot renew --dry-run
```

If the certificate already exists at those paths, skip bootstrap and issuance. The deploy hook validates and reloads nginx after successful renewals. With Cloudflare proxied DNS and a direct origin connection, select **Full (strict)** after HTTPS is ready. Private keys stay on the server and are never committed.

```sh
sudo systemctl status eglantine-web eglantine-worker
sudo journalctl -u eglantine-worker -f
curl --resolve eglantine.jvrcruz.games:443:127.0.0.1 https://eglantine.jvrcruz.games/healthz
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

Both platform builds reuse their persistent CMake/Ninja trees (`data/work/linux/linux` and `data/work/windows/windows`). Configuration runs on every attempt to pick up changed inputs; Ninja compiles only what changed. The first build starts with a fresh tree. If incremental configuration or compilation fails, the builder deletes only that platform's CMake build tree and retries configuration and compilation once. If the clean retry also fails, the build is marked failed and current downloads remain available.

Dependency downloads, ccache, Qt and the MXE toolchain persist across clean retries. Packaging always runs after successful compilation to create current versioned artifacts. A packaging or Docker startup error does not trigger a clean compilation, since deleting compiler outputs would not fix those errors. Logs identify incremental, first full, and fallback attempts.

`builder/linux.sh` follows upstream's CMake and linuxdeploy approach, using Qt 6.8.3 on Ubuntu 24.04. The `.deb` wraps the same bundled AppDir, so it does not depend on the distribution's older Qt. `builder/windows.sh` builds a pinned MXE toolchain with shared Qt 6 Widgets and Charts, Boost, FFmpeg and other dependencies, then recursively bundles DLL dependencies and Qt plugins into the ZIP. Neither build enables PGO. Toolchain source pinning is in the Windows script; linuxdeploy's continuous tools and upstream dependencies may need maintenance over time.

Publication stages the files, generates hashes and APT metadata, signs the repository, then atomically switches `data/public/current`. The HTTP server supports byte ranges for delta downloads and does not expose private state or directory listings. The source archive contains the application checkout, fetched application dependencies, and builder scripts; toolchain caches are kept separately.

## Validation

```sh
python3 -m unittest discover -s tests -v
python3 -m compileall -q service builder/windows_deps.py
bash -n builder/*.sh install.sh
node --check web/app.js
```

The incremental-build tests also require CMake, Ninja and a C compiler on the test host. They compile a small native project to verify object reuse and clean fallback after configuration or compilation errors.

Integration tests generate two signed test repositories and verify signatures, removal of superseded packages, atomic publication, failed-release preservation, HTTP ranges, HEAD requests and path traversal rejection. They use temporary data and do not publish test artifacts to the running site.

## Docker startup failures

Docker exit status 125 indicates a container startup failure, before the build script runs. The worker now includes the last 8 KiB of build output in its journal error and status metadata, rather than only the failing command. Full output remains in the build log linked on the download page.

On servers with fewer than six CPUs, the old fixed `--cpus=6` could prevent Docker from starting the container. The worker no longer passes a Docker CPU quota and reads the daemon CPU count to size compiler parallelism. After updating, restart the worker to retry immediately:

```sh
sudo systemctl restart eglantine-worker
sudo journalctl -u eglantine-worker -n 80 --no-pager
```

If startup still fails, the logged Docker error distinguishes issues such as container-name conflicts, missing Docker group access, unavailable mounts, and unsupported host limits. Do not remove an active build container without first stopping its worker.
