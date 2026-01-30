import subprocess
from importlib import resources
from pathlib import Path
from typing import Dict, List
import json
import yaml
from rich import print
from pydantic import BaseModel

from cep.utils import DATA_DIR


APP_STORE_DATA_DIR = DATA_DIR / 'app_store'
APP_STORE_DATA_DIR.mkdir(exist_ok=True)

APP_TEMPLATES_PATH = "cep.app_store.app_templates"

DEPLOYMENT_DIR = APP_STORE_DATA_DIR / "docker_deployment"
DEPLOYMENT_DIR.mkdir(exist_ok=True)
DEPLOYMENT_PATH = DEPLOYMENT_DIR / "compose.yml"


class ComposeConfig(BaseModel):
    services: Dict = {}
    networks: Dict = {}
    volumes: Dict = {}
    configs: Dict = {}
    secrets: Dict = {}

    @classmethod
    def load(cls, path: Path) -> "ComposeConfig":
        if not path.exists():
            return cls()
        data = yaml.safe_load(path.read_text()) or {}
        return cls(**data)

    def save(self, path: Path) -> None:
        path.write_text(
                yaml.safe_dump(
                    self.model_dump(mode="json"),
                    sort_keys=False
                    )
                )


class Docker():

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
                f"Available apps are {Docker.list_available_apps()}",
                ])
            raise ValueError(msg)

    @staticmethod
    def add_to_deployment_file(app_config: ComposeConfig):
        deployment_config = ComposeConfig.load(DEPLOYMENT_PATH)
        for top_level_key in ComposeConfig.__fields__.keys():
            top_level_deployment_config = getattr(deployment_config, top_level_key)
            top_level_app_config = getattr(app_config, top_level_key)
            for key, value in top_level_app_config.items():
                top_level_deployment_config[key] = value
        deployment_config.save(DEPLOYMENT_PATH)

    @staticmethod
    def print_deployment_file(compose_config: ComposeConfig):
        deployment = ComposeConfig.load(DEPLOYMENT_PATH)
        print(deployment)

    @staticmethod
    def list_available_apps() -> list[str]:
        templates = resources.files(APP_TEMPLATES_PATH)

        return [entry.name.split('.')[0] for entry in templates.iterdir()]

    @staticmethod
    def compose_up():
        subprocess.Popen(
            [
                "docker",
                "compose",
                "-f",
                DEPLOYMENT_PATH,
                "up",
                "-d"
            ],
        )

    @staticmethod
    def list_up() -> List[Dict[str, str]]:
        process = subprocess.run(
            [
                "docker",
                "ps",
                "--format",
                "json"
            ],
            capture_output=True,
            text=True,
            check=True
        )
        #TODO:check return values
        return [json.loads(line) for line in process.stdout.strip().split('\n') if line]
