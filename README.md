# Eglantine nx2 build distribution

A local build worker watches `https://github.com/Djihads80/Eglantine`, branches `nx2` and `nx2-experimental`, every two minutes. It builds on first run and when upstream commits or build scripts change; unchanged successful builds are never rebuilt on a timer. Separate Linux and Windows workers run concurrently. Each worker builds one channel at a time. Windows uses MinGW and publishes an EXE installer. AppImage, Debian packages and the signed APT repository are published immediately after Linux packaging and source archiving finish; no other platform build delays publication. A failure leaves that channel's previous release available and retries it after 30 minutes; the other channel is still checked and built. No GitHub credentials or upstream changes are needed.

## Run

Requires Linux, Python 3.11+, Docker, Git, GnuPG, `apt-ftparchive` (Ubuntu package `apt-utils`), and systemd user services. Docker must be available to your user.

```sh
cp .env.example .env    # optional: adjust the public URL or polling interval
./install.sh
loginctl enable-linger "$USER"
```

The site listens on **0.0.0.0:39402**. The installer enables `eglantine-web.service`, `eglantine-worker.service` (Linux), and `eglantine-windows-worker.service` for the current user. Linger keeps them running after logout and starts them at boot. Build containers have no Docker CPU quota. Compiler parallelism defaults to at most six jobs, clamped to the Docker daemon CPU count. Linux memory defaults to min(10 GiB, 60% of Docker host RAM). Windows defaults to three compiler jobs and min(8 GiB, 30% of Docker host RAM). `BUILD_JOBS` / `BUILD_MEMORY` and `WINDOWS_BUILD_JOBS` / `WINDOWS_BUILD_MEMORY` override the respective worker settings. Size overrides to leave room for both workers and the host. Subsequent Linux builds reuse their CMake/Ninja tree, dependencies and ccache. Ubuntu 24.04 is the Linux ABI baseline.

```sh
systemctl --user status eglantine-web eglantine-worker eglantine-windows-worker
journalctl --user -u eglantine-worker -f
curl http://127.0.0.1:39402/api/status
systemctl --user stop eglantine-worker
# Stop any active owned build container when stopping manually:
docker stop eglantine-build-linux
```

The web page shows build state, the active build log, the last successful commit, checksums, and source downloads. Each platform’s download buttons become available after its first successful build, independently of the other platform. Runtime data stays in ignored `data/`.

## Server deployment with nginx and system services

Place this repository at `/opt/apps/eglantine.jvrcruz.games`. The system units in `deploy/` run as `apps`: `eglantine-web` serves the website and `eglantine-worker` builds both Linux channels, and `eglantine-windows-worker` builds both Windows channels independently. These replace the user-service installation above on the server and start automatically at boot without a login session.

Install the prerequisites above, nginx, and Docker on the server, then run:

```sh
cd /opt/apps/eglantine.jvrcruz.games
# Create the service account only if it does not already exist.
id apps >/dev/null 2>&1 || sudo useradd --system --user-group --home-dir /opt/apps/eglantine.jvrcruz.games --no-create-home --shell /usr/sbin/nologin apps
sudo usermod -aG docker apps
sudo chown -R apps:apps /opt/apps/eglantine.jvrcruz.games
sudo install -m 0644 deploy/eglantine-web.service deploy/eglantine-worker.service deploy/eglantine-windows-worker.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now docker eglantine-web eglantine-worker eglantine-windows-worker

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
sudo systemctl status eglantine-web eglantine-worker eglantine-windows-worker
sudo journalctl -u eglantine-worker -f
curl --resolve eglantine.jvrcruz.games:443:127.0.0.1 https://eglantine.jvrcruz.games/healthz
# After pulling updated service definitions, reinstall them and daemon-reload.
sudo systemctl restart eglantine-web eglantine-worker eglantine-windows-worker
```

## Public domain

Hosting is prepared locally; Cloudflare DNS and routing will be configured separately. For Cloudflare Tunnel, point the public hostname to `http://localhost:39402`; the local service does not terminate TLS. A tunnel does not need inbound port forwarding. `deploy/cloudflared.example.yml` contains a ready-to-adapt ingress rule; for an existing tunnel, add only that hostname rule before its catch-all. Disable caching for all paths ending in `/api/status` and all `/apt/*`, `/updates/*`, `/windows/updates/*`, `/logs/*`, `/windows/logs/*` paths, including their `/nightly` equivalents; do not cache stale update metadata. Preserve HTTP Range headers and 206 responses.

Create DNS records for `eglantine.jvrcruz.games` pointing to this server, then proxy HTTPS to `127.0.0.1:39402`. An example is in `deploy/Caddyfile`. If the server is behind NAT, forward ports 80/443 to your reverse proxy. Set `PUBLIC_URL` before building: it is embedded in the AppImage metadata and the Debian update source. Changing it requires rebuilding packages.

## Downloads and updates

The website offers two channels, each with AppImage, Debian and Windows installer downloads:

| Channel | Branch | Debian package | AppImage update feed | Windows update feed |
| --- | --- | --- | --- | --- |
| nx2 | `nx2` | `eglantine` | `/updates/Eglantine-x86_64.AppImage.zsync` | `/windows/updates/latest.json` |
| Experimental nightly | `nx2-experimental` | `eglantine-nightly` | `/nightly/updates/Eglantine-nightly-x86_64.AppImage.zsync` | `/nightly/windows/updates/latest.json` |

All paths use `PUBLIC_URL` (default `https://eglantine.jvrcruz.games`). AppImages embed their channel’s own zsync feed for AppImageUpdate. Remove `.zsync` for the latest AppImage download. The emulator’s upstream update checker is disabled.

### One Debian repository, mutually exclusive packages

**Both packages are in `/apt`**, suite `stable`, component `main`, architecture `amd64`. `/nightly/apt` remains an alias for existing clients. Each signed snapshot contains the latest successfully published Debian package from each channel; until a channel first builds, only the available package is listed.

Install a downloaded `.deb` with `sudo apt install ./eglantine_amd64.deb` or `sudo apt install ./eglantine-nightly_amd64.deb`. Both configure the same `/etc/apt/sources.list.d/eglantine.list` and `/usr/share/keyrings/eglantine-archive-keyring.gpg`, pointing to the canonical `/apt` URL. Alternatively, use the repository setup commands on the website. Then select a channel:

```sh
sudo apt update
sudo apt install eglantine             # nx2
# Or switch to experimental (APT removes eglantine):
sudo apt install eglantine-nightly
```

The packages declare reciprocal `Conflicts`, so APT cannot install them together. Review APT’s removal prompt when switching. Existing installations that previously allowed both packages should remove one before upgrading. If APT reports the repository Label changing to `Eglantine`, accept this one-time migration with `sudo apt update --allow-releaseinfo-change`.

Each package installs its bundled emulator under `/opt/<package>`, a `/usr/bin/<package>` command, and an application-menu desktop launcher and icon. Updates use normal `apt update` and `apt upgrade`. Ubuntu 24.04 is the ABI baseline.

### Windows installer and automatic updates

Download `eglantine-Windows-x86_64-Setup.exe` or `eglantine-nightly-Windows-x86_64-Setup.exe` from the website. Installers target Windows 10/11 x64, bundle the emulator and required DLLs, and install per user under `%APPDATA%\eglantine` or `%APPDATA%\eglantine-nightly`, without administrator rights. They add Desktop and Start menu shortcuts and a per-user uninstaller. Uninstall the other channel before installing a different channel.

Shortcuts start `Launcher.exe`, which runs the bundled PowerShell update harness before launching the emulator. It uses built-in Windows PowerShell 5.1, checks the channel’s HTTPS feed, verifies payload size and SHA-256, safely extracts a complete replacement into a new version directory, and atomically switches the installed version. Original launch arguments are passed through to the emulator. If checking, downloading or applying an update fails, it logs the error in `update.log` and launches the installed version. The initial installer already contains a usable emulator, so first launch does not require a download.

Old local payloads are removed after an update, except those still used by a running emulator. User emulator configuration is preserved. The update feed distributes emulator payload ZIPs; changes to the launcher/harness itself require running a newer installer. Authenticity relies on HTTPS to this server; hashes detect corruption. Installers currently have no Authenticode signature.

`/api/status` retains Linux metadata and adds `channels` and per-channel `platforms` maps. Direct Windows status endpoints are `/windows/api/status` and `/nightly/windows/api/status`. Windows release URLs, source archives and logs live under those `/windows` prefixes. Linux URLs retain their existing shape. `/nightly/` redirects to the nightly website view.

### Publication, storage and retention

Channels and platforms have independent checkouts, build trees, status, logs, staging and releases. Linux stable uses `data/`, Linux nightly `data/nightly/`; Windows adds `windows/` beneath each channel root. Qt/tool downloads, ccache and the MXE toolchain persist in shared caches. A download lock protects the shared Qt host installation. Linux and Windows use different worker locks and container names.

Each successful platform build publishes immediately. Publication verifies artifacts, creates hashes and metadata, then atomically replaces that platform’s `public/current` pointer. Linux additionally signs a combined APT snapshot and atomically switches `data/public/shared-apt`. Only the latest successful release per channel and platform is retained; superseded artifacts and abandoned staging directories are discarded after publication. Failures preserve previous downloads. Logs and toolchain caches remain. Clients holding an old immutable release URL or APT index during replacement may need to refresh and retry.

APT metadata uses the shared archive key in `data/gnupg/`. **Back up this directory securely** and retain it across redeployments; losing it breaks trust for existing installations. Never publish it. Only the exported public key is mounted into Linux build containers.

## Builds

Each platform/channel reuses its own CMake/Ninja tree. Configuration runs on every attempt; Ninja compiles changed inputs. If incremental configuration or compilation fails, only that platform’s application build tree is removed and a full retry runs once. Dependencies, toolchains and ccache persist. Packaging or Docker startup errors do not trigger a clean compile. Changes to build/packaging scripts also trigger a rebuild on the next poll.

Linux uses Qt 6.8.3 with linuxdeploy. AppImage, `.deb`, source archive and signed APT metadata publish together after Linux packaging finishes. Windows independently uses cached MXE MinGW and **official precompiled Qt 6.8.3** with matching native host tools, plus upstream’s bundled precompiled SDL3. A compile/link/MOC probe validates the Qt kit; a source-built Qt fallback is available if the kit or application build fails. Other dependencies reuse cached libraries; dependencies without a compatible precompiled package are built from pinned sources. `WINDOWS_PREBUILT_LIBS=0` forces the source-built Qt path. Cold toolchain setup still takes longer than subsequent incremental builds.

To upgrade an existing server, install all three service definitions together. The Linux unit also wants the Windows unit, so starting Linux starts the independent Windows watcher. Both use the same `POLL_SECONDS` and `RETRY_SECONDS`, check immediately at startup, and build on first run, upstream commit changes and builder changes. The old `REBUILD_SECONDS` setting is ignored and can be removed from existing `.env` files. Explicit `--platform` arguments prevent a shared environment setting from selecting the wrong platform.

```sh
sudo -u apps git -C /opt/apps/eglantine.jvrcruz.games pull --ff-only
cd /opt/apps/eglantine.jvrcruz.games
sudo bash deploy/install-services.sh
sudo journalctl -u eglantine-windows-worker -f
```

The installer restarts the website and both workers, stopping any active build containers. Keep existing `data/mxe` and `data/cache` to reuse previous builds. A `git pull` alone does not install new systemd units. For a user-service installation, rerun `./install.sh` and restart both workers after pulling.

The Windows card always offers a **Windows build log** button, including before the first completed build. `/windows/logs/latest.log` and `/nightly/windows/logs/latest.log` serve the latest attempt for their channel, or the Windows watcher log when no attempt exists yet. The watcher log records startup settings, branch checks, build triggers, retry scheduling and errors that occur before a build log is created. The durable watcher log is `/windows/logs/watcher.log`; systemd startup failures remain visible in the journal.

The HTTP server supports byte ranges and does not expose private state or directory listings. Source archives include the application checkout, fetched application dependencies and builder scripts; Windows archives also include the installer/update harness sources. Toolchain caches are kept separately.

## Validation

```sh
python3 -m unittest discover -s tests -v
python3 -m compileall -q service builder
bash -n builder/*.sh install.sh
node --check web/app.js
```

The incremental-build tests also require CMake, Ninja and a C compiler on the test host. They compile a small native project to verify object reuse and clean fallback after configuration or compilation errors.

Integration tests verify signed shared APT snapshots, candidates for both packages from one source, reciprocal package conflicts, independent Linux/Windows publication, channel isolation, superseded artifact removal, failure preservation, HTTP ranges, HEAD requests and path traversal rejection. They use temporary data and do not publish test artifacts to the running site.

## Docker startup failures

Docker exit status 125 indicates a container startup failure, before the build script runs. The worker now includes the last 8 KiB of build output in its journal error and status metadata, rather than only the failing command. Full output remains in the build log linked on the download page.

On servers with fewer than six CPUs, the old fixed `--cpus=6` could prevent Docker from starting the container. The worker no longer passes a Docker CPU quota and reads the daemon CPU count to size compiler parallelism. After updating, restart the worker to retry immediately:

```sh
sudo systemctl restart eglantine-worker
sudo journalctl -u eglantine-worker -n 80 --no-pager
```

If startup still fails, the logged Docker error distinguishes issues such as container-name conflicts, missing Docker group access, unavailable mounts, and unsupported host limits. Do not remove an active build container without first stopping its worker.

The PowerShell updater core can be tested on Linux with the official PowerShell container:

```sh
docker run --rm -v "$PWD:/repo:ro" mcr.microsoft.com/powershell:7.4-ubuntu-22.04 pwsh -NoLogo -NoProfile -File /repo/tests/windows/test_updater.ps1
```

This checks parsing, safe extraction, traversal/ADS rejection, payload verification, feed origin/channel validation and atomic version metadata. It does not replace an end-to-end launcher/update test on native Windows PowerShell 5.1.
