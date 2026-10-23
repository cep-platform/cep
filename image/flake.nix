
# ENV PYTHONDONTWRITEBYTECODE=1
# ENV PYTHONUNBUFFERED=1
# ENV PATH="/root/.local/bin:${PATH}"

# WORKDIR /app

# COPY ./startupscripts/start_client.sh /app/start.sh
# COPY ./startupscripts/client_banner.txt /app/client_banner.txt

# Copy dependency files first (for caching)
# COPY pyproject.toml ./
# RUN uv sync

# Copy source code
# COPY src/ src/
# RUN uv pip install -e .

# Pre-download nebula binaries and set execute permissions at build time (otherwuise cross platform bugs)
# RUN uv run python -c "from cep.utils import download_nebula; download_nebula()"

# CMD ["uv", "run", "cep", "server", "run"]

{
  description = "Cep container";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-26.05";

  outputs = { self, nixpkgs }:
    let
      system = "x86_64-linux";
    in {
      nixosConfigurations.appstore = nixpkgs.lib.nixosSystem {
        inherit system;

        modules = [
          "${nixpkgs}/nixos/modules/virtualisation/lxc-container.nix"

          ({ pkgs, ... }: {
            system.stateVersion = "26.05";

            networking.hostName = "cep";
            networking.nftables.enable = true;

            environment.systemPackages = with pkgs; [
              incus
              curl
              python3
              uv
            ];

            virtualisation.incus.enable = true;
            virtualisation.incus.preseed = {
              networks = [
                {
                  config = {
                    "ipv4.address" = "10.0.200.1/24";
                    "ipv4.nat" = "true";
                  };
                  name = "incusbr0";
                  type = "bridge";
                }
              ];
              profiles = [
                {
                  config = {
                    security.privileged = true;
                  };
                  devices = {
                    eth0 = {
                      name = "eth0";
                      network = "incusbr0";
                      type = "nic";
                    };
                    root = {
                      path = "/";
                      pool = "default";
                      size = "35GiB";
                      type = "disk";
                    };
                  };
                  name = "default";
                }
              ];
              storage_pools = [
                {
                  config = {
                    source = "/var/lib/incus/storage-pools/default";
                  };
                  driver = "dir";
                  name = "default";
                }
              ];
            };
          })
        ];
      };
    };
}

