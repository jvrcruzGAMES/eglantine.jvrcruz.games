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

    def storage(self, root):
        return root / self.directory if self.directory else root

    def public(self):
        return asdict(self)


STABLE = Channel('stable', 'nx2', 'eglantine', 'Eglantine', 'Eglantine-x86_64.AppImage')
NIGHTLY = Channel('nightly', 'nx2-experimental', 'eglantine-nightly', 'Eglantine Nightly',
                  'Eglantine-nightly-x86_64.AppImage', 'nightly', '/nightly')
CHANNELS = (STABLE, NIGHTLY)
