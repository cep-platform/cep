{
  description = "Cep NixOS host configuration (the incus host cep runs on)";

  # Host system packages/config. The host currently runs this flake with:
  #   nixos-rebuild switch --flake ./nix#incus --impure
  # (--impure because of the /etc/nixos/configuration.nix import below).
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-25.11";
  inputs.pi.url = "github:earendil-works/pi/stable";

  # Pinned so incus stays on the 7.0.x LTS: this revision carries
  # incus-lts 7.0.1 (including the security backports on top of it),
  # independent of what the main nixpkgs input does.
  inputs.nixpkgs-incus.url = "github:NixOS/nixpkgs/601cdefea293a16b71e52bd8f36f2c366f5a3d02";

  outputs = { self, nixpkgs, nixpkgs-incus, pi, ... }:
  let
    system = "x86_64-linux";
    pkgsIncus = nixpkgs-incus.legacyPackages.${system};
  in {
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

        # Impure: this host's machine config (hostname, disks, users).
        /etc/nixos/configuration.nix

        ./modules/base.nix
        ./modules/networking.nix
        ./modules/packages.nix
        ./modules/incus.nix
      ];
    };
  };
}
