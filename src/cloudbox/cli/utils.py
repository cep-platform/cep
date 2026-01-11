from pathlib import Path

from cloudbox.utils import DATA_DIR

CLI_DATA_DIR = DATA_DIR / 'cli'
CLI_DATA_DIR.mkdir(exist_ok=True)
CLOUDBOXCFG_PATH = Path('~/.cloudboxcfg')
