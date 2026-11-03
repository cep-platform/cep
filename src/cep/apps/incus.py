import os
import shutil
import subprocess
from importlib import resources
from pathlib import Path
from typing import Dict, List
import json
import yaml
from pydantic import BaseModel

from cep.utils import DATA_DIR
import logging

from rich import print  # noqa

APP_STORE_DATA_DIR = DATA_DIR / 'apps'
APP_STORE_DATA_DIR.mkdir(exist_ok=True)

APP_TEMPLATES_PATH = "cep.apps.app_templates"

PROXY_PORT_LABEL = "cep.proxy.port"

DEPLOYMENT_DIR = APP_STORE_DATA_DIR / "docker_deployment"
DEPLOYMENT_DIR.mkdir(exist_ok=True)

DESTROY_STATE_DIR = APP_STORE_DATA_DIR / "docker_down_state"
DESTROY_STATE_DIR.mkdir(exist_ok=True)

logging.basicConfig(
        filename=DESTROY_STATE_DIR / Path('docker_compose.log'),
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
        )
LOGGER = logging.getLogger(__name__)


class ComposeConfig(BaseModel):
    services: Dict = {}
    networks: Dict = {}
    volumes: Dict = {}
    configs: Dict = {}
    secrets: Dict = {}

    @classmethod
    def load(cls, path: Path) -> "ComposeConfig":
        try:
            data = yaml.safe_load(path.read_text())
            return cls(**data)
        except FileNotFoundError:
            return cls(**{})

    def save(self, path: Path) -> None:
        path.write_text(
                yaml.safe_dump(
                    self.model_dump(mode="json"),
                    sort_keys=False
                    )
                )

    @property
    def name(self):
        return self.services[0]


class Incus():

    @staticmethod
    def get_app_template(name) -> ComposeConfig:
        with resources.as_file(
                resources.files(APP_TEMPLATES_PATH).joinpath(f"{name}.yml")
                ) as template_path:

            path = Path(template_path)
            if path.exists():
                with open(path, 'r') as f:
                    config = yaml.safe_load(f)
                    compose_config = ComposeConfig(**config)
                    return compose_config

            msg = "\n".join([
                f"App {name} not found in template path {path.parent}",
                f"Available apps are {Incus.list_available_apps()}",
                ])
            raise ValueError(msg)

    #TODO: test_this: validate templates
    @staticmethod
    def add_to_deployment(app_id: str, app_config: ComposeConfig):
        app_deployment_dir = DEPLOYMENT_DIR / f"{app_id}"
        os.makedirs(app_deployment_dir, exist_ok=True)
        app_deployment_path = app_deployment_dir / f"compose.yml"
        app_config.save(app_deployment_path)

    #TODO: test_this: validate templates
    @staticmethod
    def remove_from_deployment(app_id: str):
        app_deployment_dir = DEPLOYMENT_DIR / f"{app_id}"
        try:
            shutil.rmtree(app_deployment_dir)
        except FileNotFoundError:
            LOGGER.info(
                "No deployment directory for app '%s'; nothing to remove",
                app_id,
            )

    @staticmethod
    def list_available_apps() -> list[str]:
        templates = resources.files(APP_TEMPLATES_PATH)

        return [entry.name.split('.')[0] for entry in templates.iterdir()]

    @staticmethod
    def compose_up(app_id):
        deployment_path = DEPLOYMENT_DIR / Path(app_id) / Path("compose.yml")
        subprocess.run(
                [
                    "incus-compose",
                    "-f", deployment_path,
                    "up",
                    "--no-healthd",
                    "--recreate",
                    "-d",
                    ],
                check=True,
                )

    @staticmethod
    def compose_down(app_id):
        deployment_path = DEPLOYMENT_DIR / Path(app_id) / Path("compose.yml")
        subprocess.run(
                [
                    "incus-compose",
                    "-f", deployment_path,
                    "down",
                    ],
                check=True,
                )

    @staticmethod
    def list_() -> List[Dict[str, str]]:
        process = subprocess.run(
                [
                    "incus",
                    "list",
                    "--format",
                    "json"
                    ],
                capture_output=True,
                text=True,
                check=True
                )
        return json.loads(process.stdout.strip())

    @staticmethod
    def info(app_id) -> List[Dict[str, str]]:
        process = subprocess.run(
                [
                    "incus",
                    "info",
                    app_id,
                    "--format",
                    "json"
                    ],
                capture_output=True,
                text=True,
                check=True
                )
        return json.loads(process.stdout.strip())
