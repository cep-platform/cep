# from cloudbox.utils import
from importlib import resources
from pathlib import Path


def get_app_template_path(name):
    with resources.as_file(
            resources.files("cloudbox.app_store.app_templates").joinpath(name)
            ) as template_path:
        path = Path(template_path)
        print(path)
        return path if path.exists() else None



get_app_template_path("mongo.yml")
