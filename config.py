import os
from pathlib import Path

DOWNLOAD_ROOT = Path(os.environ.get("LIGHTROOM_DOWNLOAD_ROOT", r"G:\Lightroom Download")).expanduser()
