# Eglantine nx2 build distribution

A local build worker watches `https://github.com/Djihads80/Eglantine`, branch `nx2`, every two minutes. It compiles Linux x86_64 and cross-compiles Windows x86_64 with MinGW using MXE. Only a complete set of packages is published. A failure leaves the previous release available and retries after 30 minutes. No GitHub credentials or upstream changes are needed.

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

APT metadata is signed with the locally generated archive key. **Back up `data/gnupg/` securely** and retain it across redeployments; losing it breaks trust for existing installations. Never publish that directory. Only the public key is mounted into the build container. Previous packages and by-hash indexes are retained, so clients can finish downloads during a release switch. No automatic retention policy deletes releases; monitor disk use.

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

Integration tests generate two signed test repositories and verify signatures, retained packages, atomic publication, failed-release preservation, HTTP ranges, HEAD requests and path traversal rejection. They use temporary data and do not publish test artifacts to the running site.
