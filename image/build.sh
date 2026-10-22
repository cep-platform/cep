nix build \
  .#nixosConfigurations.appstore.config.system.build.metadata \
  --print-out-paths

nix build \
  .#nixosConfigurations.appstore.config.system.build.squashfs \
  --print-out-paths

