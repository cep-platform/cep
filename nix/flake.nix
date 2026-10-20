{
  description = "Cep NixOS configuration";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-25.11";
  inputs.pi.url = "github:earendil-works/pi/stable";

  # Nix-built OCI image for the cep containers, consumed by incus-compose's
  # nix2container builder (no docker/podman/buildah needed on the host).
  inputs.nix2container.url = "github:nlewo/nix2container";

  # Pinned so incus stays on the 7.0.x LTS: this revision carries
  # incus-lts 7.0.1 (including the security backports on top of it),
  # independent of what the main nixpkgs input does.
  inputs.nixpkgs-incus.url = "github:NixOS/nixpkgs/601cdefea293a16b71e52bd8f36f2c366f5a3d02";

  outputs = { self, nixpkgs, nixpkgs-incus, pi, nix2container, ... }:
  let
    system = "x86_64-linux";
    pkgsIncus = nixpkgs-incus.legacyPackages.${system};
    pkgs = nixpkgs.legacyPackages.${system};
    cepImage = import ./image.nix {
      inherit pkgs self;
      nix2container = nix2container.packages.${system}.nix2container;
    };
  in {
    packages.${system} = {
      # OCI image descriptor built by `incus-compose build` via the service
      # build block: x-incus-compose: { builder = nix2container; args = [ ./nix#cep-image ]; }
      cep-image = cepImage.image;
      # The plain cep application (Python env from nixpkgs) - smoke-test target:
      #   nix build ./nix#cep && ./result/bin/cep --help
      cep = cepImage.cep;
    };

    nixosConfigurations.incus = nixpkgs.lib.nixosSystem {
      inherit system;

      modules = [
        {
          nixpkgs.overlays = [
            pi.overlays.default
            # virtualisation.incus uses pkgs.incus-lts by default;
            # pin it to the 7.0.1 LTS from the nixpkgs-incus input.
            (_: _: { incus-lts = pkgsIncus.incus-lts; })
          ];
        }

        /etc/nixos/configuration.nix

        ./modules/base.nix
        ./modules/networking.nix
        ./modules/packages.nix
        ./modules/incus.nix
      ];
    };
  };
}
