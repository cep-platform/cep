import pickle
from typing import Dict
from pathlib import Path


def dump_logs(logger, process):

    stdout, stderr = process.communicate()

    logger.info(f"Compose down completed with return code {process.returncode}")
    if stdout:
        logger.info(f"stdout: {stdout.decode()}")
    if stderr:
        logger.error(f"stderr: {stderr.decode()}")
    if process.returncode != 0:
        logger.error(f"Compose down failed with code {process.returncode}")




# TODO: mutate file tracking state
def dump_state(payload: Dict[str, Dict[str, str]], name: str, path: Path):
    if not path.exists():
        return FileNotFoundError

    with open(path, 'wb') as f:
        pickle.dump(payload, f)

    print("Saved state for {0} app in {1}".format(path, name))

def read_metadata(name: str):
    return NotImplementedError


def verify_state():
    return NotImplementedError
