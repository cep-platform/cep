
{
  description = "Minimal NixOS container for Cep app store testing";

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

            networking.hostName = "cep-appstore";
            networking.nftables.enable = true;

            environment.systemPackages = with pkgs; [
              incus
              incus-compose
              curl
              python3
              uv
            ];

            virtualisation.incus.enable = true;
          })
        ];
      };
    };
}

