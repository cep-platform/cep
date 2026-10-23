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
  --alias cep

incus image list
incus launch cep $1 \
  --config security.nesting=true

incus exec cep -- curl --version
incus exec cep -- incus version
