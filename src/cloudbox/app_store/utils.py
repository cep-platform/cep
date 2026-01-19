import os
from result import Result, Ok, Err

from typing import List

APP_TEMPLATE_PATH = os.getcwd() + "/src/cloudbox/app-templates/"

def get_available_path_templates(app_name: str) -> Result[List[str], str]:
    files = [f for f in os.listdir(APP_TEMPLATE_PATH)] 
    if len(files) > 0:
        # I assume template naming cannot fail
        config_match = any([app.split(".yml")[0] == app_name  for app in files])
        if config_match:
            return Ok(
                APP_TEMPLATE_PATH + app_name + ".yml"
            )
        return Err("App not found in template directory")

    return Err("Pointing to inexistent directory")


def fetch_image_configs(app_name) -> Result[str, FileNotFoundError]:
    config_path =  get_available_path_templates(app_name)
    if config_path.is_err:
        return config_path
    return config_path

