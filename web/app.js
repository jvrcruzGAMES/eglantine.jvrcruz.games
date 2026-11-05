const origin = location.origin;
const selected = new URLSearchParams(location.search).get('channel') === 'nightly' ? 'nightly' : 'stable';
const definitions = {
  stable: {name:'stable', branch:'nx2', package:'eglantine', title:'Eglantine', prefix:'', appimage:'Eglantine-x86_64.AppImage'},
  nightly: {name:'nightly', branch:'nx2-experimental', package:'eglantine-nightly', title:'Eglantine Nightly', prefix:'/nightly', appimage:'Eglantine-nightly-x86_64.AppImage'}
};
function renderDefinition(channel) {
  document.title = `${channel.title} · ${channel.branch} builds`;
  document.querySelector('#branch').textContent = channel.branch;
  document.querySelector('#channel-name').textContent = channel.name === 'nightly' ? 'THE EXPERIMENTAL NIGHTLY CHANNEL' : 'THE NX2 CHANNEL';
  document.querySelector('#channel-description').textContent = channel.name === 'nightly'
    ? 'Experimental builds, packaged as eglantine-nightly. Install one Debian channel at a time.'
    : 'The nx2 channel, packaged as eglantine. Install one Debian channel at a time.';
  document.querySelector('#upstream-source').href = `https://github.com/Djihads80/Eglantine/tree/${channel.branch}`;
  document.querySelectorAll('[data-channel]').forEach(link => {
    if (link.dataset.channel === selected) link.setAttribute('aria-current', 'page');
    else link.removeAttribute('aria-current');
  });
  document.querySelector('[data-kind="appimage"]').dataset.artifact = channel.appimage;
  document.querySelector('[data-kind="deb"]').dataset.artifact = `${channel.package}_amd64.deb`;
  document.querySelector('#apt').textContent = `sudo install -d -m 0755 /usr/share/keyrings
curl -fsSL ${origin}/eglantine-archive-keyring.gpg | sudo tee /usr/share/keyrings/eglantine-archive-keyring.gpg > /dev/null
echo "deb [arch=amd64 signed-by=/usr/share/keyrings/eglantine-archive-keyring.gpg] ${origin}/apt stable main" | sudo tee /etc/apt/sources.list.d/eglantine.list
sudo apt update
sudo apt install ${channel.package}`;
  document.querySelector('#zsync').textContent = `${origin}${channel.prefix}/updates/${channel.appimage}.zsync`;
  document.querySelector('#appimage-url').href = `${channel.prefix}/updates/${channel.appimage}`;
}
renderDefinition(definitions[selected]);
async function refresh() {
  try {
    const response = await fetch('/api/status', {cache:'no-store'});
    if (!response.ok) throw new Error('Status unavailable');
    const all = await response.json();
    const status = all.channels?.[selected] || (selected === 'stable' ? all : {phase:'waiting'});
    const channel = status.definition || definitions[selected];
    renderDefinition(channel);
    const labels = {waiting:'Waiting for the first build', building:`Building Linux · ${(status.commit || '').slice(0,12)}`, ready:`Watching ${channel.branch} · up to date`, failed:'Build failed · automatic retry scheduled'};
    document.querySelector('#status').textContent = labels[status.phase] || `Watching ${channel.branch}`;
    const log = document.querySelector('#log');
    log.hidden = !status.log;
    if (status.log) log.href = status.log;
    const windows = status.platforms?.windows || {phase:'waiting'};
    const windowsLink = document.querySelector('#windows-download');
    const installer = windows.latest?.artifacts.find(a => a.name.endsWith('-Setup.exe'));
    document.querySelector('#windows-status').textContent = windows.phase === 'building' ? 'Windows build in progress · Linux downloads remain available' : windows.phase === 'failed' ? 'Windows build failed · retry scheduled' : windows.latest ? `Windows · ${windows.latest.commit.slice(0,12)}` : 'Waiting for the first Windows build';
    if (installer) {
      windowsLink.href = installer.url; windowsLink.removeAttribute('aria-disabled');
      windowsLink.textContent = `Download installer ↓ · ${Math.round(installer.bytes/1024/1024)} MB`;
    } else {
      windowsLink.removeAttribute('href'); windowsLink.setAttribute('aria-disabled','true');
      windowsLink.textContent = 'Awaiting first Windows build';
    }
    const windowsLog = document.querySelector('#windows-log');
    windowsLog.hidden = !windows.log; if (windows.log) windowsLog.href = windows.log;
    const release = status.latest;
    document.querySelector('#release').textContent = release
      ? `${release.commit.slice(0,12)} · ${new Date(release.published_at).toLocaleString()}`
      : 'No release published yet';
    document.querySelectorAll('[data-artifact]').forEach(link => {
      const artifact = release?.artifacts.find(a => a.name === link.dataset.artifact);
      if (!artifact) {
        link.removeAttribute('href'); link.setAttribute('aria-disabled', 'true');
        link.textContent = 'Awaiting first build'; return;
      }
      link.href = artifact.url;
      link.removeAttribute('aria-disabled');
      link.textContent = `Download ↓ · ${Math.round(artifact.bytes / 1024 / 1024)} MB`;
    });
    const verification = document.querySelector('#verification');
    verification.replaceChildren();
    const links = [];
    for (const [platform, published, prefix] of [
      ['Linux', release, channel.prefix], ['Windows', windows.latest, `${channel.prefix}/windows`]
    ]) {
      if (!published) continue;
      links.push([`${platform} SHA256 checksums`, `${prefix}/releases/${published.version}/SHA256SUMS`]);
      const source = published.artifacts.find(a => a.name === 'source.tar.gz');
      if (source) links.push([`${platform} source archive`, source.url]);
    }
    if (!links.length) verification.textContent = 'Available after the first successful build.';
    for (const [label, url] of links) {
      const link = document.createElement('a'); link.textContent = `${label} ↗`; link.href = url;
      verification.append(link, document.createElement('br'));
    }
  } catch {
    document.querySelector('#status').textContent = 'Build status temporarily unavailable';
  }
}
refresh(); setInterval(refresh, 30000);
