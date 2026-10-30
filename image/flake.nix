{
  description = "Cep OCI image, built with nix2container (no Docker daemon needed)";

  # nixos-26.05 carries python313 and the deps cep needs (see image.nix).
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-26.05";

  # The image builder. The canonical home is nlewo/nix2container
  # (github:nix-community/nix2container does not exist).
  inputs.nix2container.url = "github:nlewo/nix2container";

  outputs = { self, nixpkgs, nix2container }:
    let
      system = "x86_64-linux";
      pkgs = nixpkgs.legacyPackages.${system};
      nix2container-pkgs = nix2container.packages.${system};
      # nix >= 2.28 makes a flake in a git subdirectory see only its
      # subtree as `self`; the repo root (pyproject.toml, src/,
      # startupscripts/) is its parent directory in the store tree.
      repoRoot = dirOf self.outPath;
      cepImage = import ./image.nix {
        inherit pkgs repoRoot;
        nix2container = nix2container-pkgs.nix2container;
      };
    in {
      packages.${system} = {
        # The image descriptor (image.json + streamed layers).
        # Consumers:
        #   - image/build.sh materializes it and imports it into Incus
        #   - `nix run ./image#cep-image.copyTo -- <skopeo-dest>` pushes it to
        #     any registry/skopeo target
        cep-image = cepImage.image;

        # The plain cep application (Python env from nixpkgs) - smoke-test
        # target:
        #   nix build ./image#cep && ./result/bin/cep --help
        cep = cepImage.cep;

        # skopeo with the nix: transport, used by image/build.sh to
        # materialize the image as an OCI layout.
        skopeo-nix2container = nix2container-pkgs.skopeo-nix2container;
      };
    };
}
