FROM rayproject/ray:latest

ARG NEBULA_VERSION=1.10.0
ARG TARGETARCH

USER root

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    unzip \
    ca-certificates \
    iproute2 \
    && rm -rf /var/lib/apt/lists/*

RUN case "${TARGETARCH}" in \
      amd64) ARCH="amd64" ;; \
      arm64) ARCH="arm64" ;; \
      *) echo "Unsupported arch: ${TARGETARCH}" && exit 1 ;; \
    esac && \
    curl -fsSL "https://github.com/slackhq/nebula/releases/download/v${NEBULA_VERSION}/nebula-linux-${ARCH}.tar.gz" \
      -o /tmp/nebula.tar.gz && \
    tar -xzf /tmp/nebula.tar.gz -C /usr/local/bin/ && \
    rm /tmp/nebula.tar.gz && \
    chmod +x /usr/local/bin/nebula /usr/local/bin/nebula-cert

COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
