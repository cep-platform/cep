#!/usr/bin/env bash
set -euo pipefail

cd /app

uv sync --locked

uv run python -c "from cep.utils import download_nebula; download_nebula()"

exec uv run cep "$@"
