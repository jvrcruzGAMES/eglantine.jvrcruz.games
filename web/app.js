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
    ? 'Experimental builds, packaged separately as eglantine-nightly.'
    : 'The nx2 channel, packaged as eglantine.';
  document.querySelector('#upstream-source').href = `https://github.com/Djihads80/Eglantine/tree/${channel.branch}`;
  document.querySelectorAll('[data-channel]').forEach(link => {
    if (link.dataset.channel === selected) link.setAttribute('aria-current', 'page');
    else link.removeAttribute('aria-current');
  });
  document.querySelector('[data-kind="appimage"]').dataset.artifact = channel.appimage;
  document.querySelector('[data-kind="deb"]').dataset.artifact = `${channel.package}_amd64.deb`;
  document.querySelector('#apt').textContent = `sudo install -d -m 0755 /etc/apt/keyrings
curl -fsSL ${origin}/eglantine-archive-keyring.gpg | sudo tee /etc/apt/keyrings/${channel.package}.gpg > /dev/null
echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/${channel.package}.gpg] ${origin}${channel.prefix}/apt stable main" | sudo tee /etc/apt/sources.list.d/${channel.package}.list
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
    if (!release) { verification.textContent = 'Available after the first successful build.'; return; }
    const source = release.artifacts.find(a => a.name === 'source.tar.gz');
    const links = [['SHA256 checksums', `${channel.prefix}/releases/${release.version}/SHA256SUMS`]];
    if (source) links.push(['Source archive', source.url]);
    for (const [label, url] of links) {
      const link = document.createElement('a'); link.textContent = `${label} ↗`; link.href = url;
      verification.append(link, document.createElement('br'));
    }
  } catch {
    document.querySelector('#status').textContent = 'Build status temporarily unavailable';
  }
}
refresh(); setInterval(refresh, 30000);
