from __future__ import annotations

from importlib import resources
from pathlib import Path

from platformdirs import user_data_dir


APP_NAME = "cloudbox"
DB_PATH = Path(user_data_dir(APP_NAME)) / 'db.json'


def get_executable_path(name):
    with resources.as_file(resources.files("cloudbox.executables").joinpath(name)) as exe_path:
        path = Path(exe_path)
        path.chmod(0o755)
        return path if path.exists() else None


def get_template_path(name):
    with resources.as_file(
            resources.files("cloudbox.templates").joinpath(name)
            ) as template_path:
        path = Path(template_path)
        return path if path.exists() else None
