const origin = location.origin;
document.querySelector('#apt').textContent = `sudo install -d -m 0755 /etc/apt/keyrings
curl -fsSL ${origin}/eglantine-archive-keyring.gpg | sudo tee /etc/apt/keyrings/eglantine.gpg > /dev/null
echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/eglantine.gpg] ${origin}/apt stable main" | sudo tee /etc/apt/sources.list.d/eglantine.list
sudo apt update
sudo apt install eglantine`;
document.querySelector('#zsync').textContent = `${origin}/updates/Eglantine-x86_64.AppImage.zsync`;
async function refresh() {
  try {
    const response = await fetch('/api/status', {cache:'no-store'});
    if (!response.ok) throw new Error('Status unavailable');
    const status = await response.json();
    const labels = {waiting:'Waiting for the first build', building:`Building Linux · ${(status.commit || '').slice(0,12)}`, ready:'Watching nx2 · up to date', failed:'Build failed · automatic retry scheduled'};
    document.querySelector('#status').textContent = labels[status.phase] || 'Watching nx2';
    const log = document.querySelector('#log');
    log.hidden = !status.log;
    if (status.log) log.href = status.log;
    if (!status.latest) return;
    const release = status.latest;
    document.querySelector('#release').textContent = `${release.commit.slice(0,12)} · ${new Date(release.published_at).toLocaleString()}`;
    document.querySelectorAll('[data-artifact]').forEach(link => {
      const artifact = release.artifacts.find(a => a.name === link.dataset.artifact);
      if (!artifact) return;
      link.href = artifact.url;
      link.removeAttribute('aria-disabled');
      link.textContent = `Download ↓ · ${Math.round(artifact.bytes / 1024 / 1024)} MB`;
    });
    const verification = document.querySelector('#verification');
    verification.replaceChildren();
    for (const [label, url] of [['SHA256 checksums', `/releases/${release.version}/SHA256SUMS`], ['Source archive', release.artifacts.find(a => a.name === 'source.tar.gz').url]]) {
      const link = document.createElement('a'); link.textContent = `${label} ↗`; link.href = url;
      verification.append(link, document.createElement('br'));
    }
  } catch {
    document.querySelector('#status').textContent = 'Build status temporarily unavailable';
  }
}
refresh(); setInterval(refresh, 30000);
