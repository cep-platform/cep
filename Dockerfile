FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PATH="/root/.local/bin:${PATH}"

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends incus

RUN incus admin init --minimal

COPY ./startupscripts/start_client.sh /app/start.sh
COPY ./startupscripts/client_banner.txt /app/client_banner.txt

# Copy dependency files first (for caching)
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
COPY pyproject.toml ./
RUN uv sync

# Copy source code
COPY src/ src/
RUN uv pip install -e .

# Pre-download nebula binaries and set execute permissions at build time (otherwuise cross platform bugs)
RUN uv run python -c "from cep.utils import download_nebula; download_nebula()"

CMD ["uv", "run", "cep", "server", "run"]

