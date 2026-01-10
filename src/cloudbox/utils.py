from __future__ import annotations

import platform
import stat
import tarfile
import urllib.request
import zipfile
from importlib import resources
from pathlib import Path

from platformdirs import user_data_dir


APP_NAME = "cloudbox"
DB_PATH = Path(user_data_dir(APP_NAME)) / 'db.json'
CACHE_DIR = Path.home() / ".cache" / "nebula"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


NEBULA_VERSION = "1.10.0"

NEBULA_DOWNLOAD_CONFIG = {
    "linux-amd64": {
        "url": f"https://github.com/slackhq/nebula/releases/download/v{NEBULA_VERSION}/nebula-linux-amd64.tar.gz",
        "archive_type": "tar.gz",
        "sha256": "…",
    },
    "darwin-amd64": {
        "url": f"https://github.com/slackhq/nebula/releases/download/v{NEBULA_VERSION}/nebula-darwin.zip",
        "archive_type": "zip",
        "sha256": "…",
    },
}


def get_platform():
    machine = platform.machine().lower()
    system = platform.system().lower()

    if system == "linux" and machine in ("x86_64", "amd64"):
        platform_name = "linux-amd64"
    elif system == "darwin" and machine in ("arm64", "aarch64"):
        platform_name = "darwin-arm64"
    elif system == "darwin":
        platform_name = "darwin-amd64"
    elif system == "windows":
        platform_name = "windows-amd64.exe"

    return platform_name


def extract_archive(
        archive_path: Path,
        archive_type: str,
        target_dir: Path,
        ) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)

    if archive_type == "zip":
        with zipfile.ZipFile(archive_path) as zf:
            zf.extractall(target_dir)
    elif archive_type in ("tar.gz"):
        with tarfile.open(archive_path, "r:gz") as tf:
            tf.extractall(target_dir)
    else:
        raise ValueError(f"Unsupported archive type: {archive_type}")


def download_nebula():

    platform_name = get_platform()

    nebula_download_config = NEBULA_DOWNLOAD_CONFIG.get(platform_name, None)
    if nebula_download_config is None:
        raise RuntimeError(f"Unsupported platform: {platform_name}")

    nebula_path = CACHE_DIR / "nebula"
    nebula_cert_path = CACHE_DIR / "nebula-cert"

    if not nebula_path.exists():
        archive_path = CACHE_DIR / 'archive'
        url = nebula_download_config['url']
        urllib.request.urlretrieve(url, archive_path)
        extract_archive(
                archive_path=archive_path,
                archive_type=nebula_download_config['archive_type'],
                target_dir=CACHE_DIR,
                )
        nebula_path.chmod(nebula_path.stat().st_mode | stat.S_IEXEC)
        nebula_path.chmod(nebula_cert_path.stat().st_mode | stat.S_IEXEC)
        archive_path.unlink()


def get_executable_path(name):
    if name not in ['nebula', 'nebula-cert']:
        raise ValueError(f"Unsupported executable: {name} should be in ['nebula', 'nebula-cert']")

    path = CACHE_DIR / name
    if not path.exists():
        download_nebula()
    return path


def get_template_path(name):
    with resources.as_file(
            resources.files("cloudbox.templates").joinpath(name)
            ) as template_path:
        path = Path(template_path)
        return path if path.exists() else None
