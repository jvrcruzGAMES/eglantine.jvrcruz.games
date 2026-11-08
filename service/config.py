import os
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
DATA = Path(os.environ.get('EGLANTINE_DATA', ROOT / 'data')).resolve()
PUBLIC_URL = os.environ.get('PUBLIC_URL', 'https://eglantine.jvrcruz.games').rstrip('/')
UPSTREAM = 'https://github.com/Eglantine-Community/Eglantine.git'
