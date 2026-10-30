META=$(nix build \
  .#nixosConfigurations.appstore.config.system.build.metadata \
  --print-out-paths)

ROOTFS=$(nix build \
  .#nixosConfigurations.appstore.config.system.build.squashfs \
  --print-out-paths)

ls "$META/tarball"
ls "$ROOTFS"

incus image import \
  "$META"/tarball/*.tar.xz \
  "$ROOTFS"/*.squashfs \
  --project incus-compose-cache \
  --alias local/cep:latest
