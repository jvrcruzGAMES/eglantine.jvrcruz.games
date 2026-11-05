from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Channel:
    name: str
    branch: str
    package: str
    title: str
    appimage: str
    directory: str = ''
    prefix: str = ''

    def storage(self, root, platform='linux'):
        data = root / self.directory if self.directory else root
        return data / 'windows' if platform == 'windows' else data

    @property
    def installer(self):
        return self.package + '-Windows-x86_64-Setup.exe'

    def public(self):
        return dict(asdict(self), installer=self.installer)


STABLE = Channel('stable', 'nx2', 'eglantine', 'Eglantine', 'Eglantine-x86_64.AppImage')
NIGHTLY = Channel('nightly', 'nx2-experimental', 'eglantine-nightly', 'Eglantine Nightly',
                  'Eglantine-nightly-x86_64.AppImage', 'nightly', '/nightly')
CHANNELS = (STABLE, NIGHTLY)
