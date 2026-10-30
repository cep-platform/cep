#!/usr/bin/env bash
set -euo pipefail

META=$(nix build \
  .#nixosConfigurations.appstore.config.system.build.metadata \
  --print-out-paths)

ROOTFS=$(nix build \
  .#nixosConfigurations.appstore.config.system.build.squashfs \
  --print-out-paths)

ls "$META/tarball"
ls "$ROOTFS"

CACHE_PROJECT=incus-compose-cache
# incus-compose maps the compose file's `image: localhost/cep:latest`
# (podman-style "localhost") to the incus image name `local/cep:latest`, and
# looks it up in the cache project under "<name>/<platform>" (see cacheAlias()
# in lxc/incus-compose client/resource_image.go). With no `platform:` in the
# compose file, the platform is the server's architecture mapped to registry
# spelling: x86_64 -> "amd64". Keep the plain alias too for readable
# `incus image list --all-projects` output.
NAME=local/cep:latest
PLATFORM_ALIAS=local/cep:latest/amd64

# Drop any previous cep import first: nix builds are deterministic, so an
# unchanged rebuild re-imports the same fingerprint, which incus rejects with
# "Image with same fingerprint already exists". The aliases contain ':' and
# are awkward to address through the CLI, so resolve them to fingerprints.
image_json=$(incus image list --project "$CACHE_PROJECT" --format json)
old_fps=$(python3 -c '
import json, sys
names = set(sys.argv[1:])
for img in json.loads(sys.stdin.read()):
    if any(a["name"] in names for a in img.get("aliases", [])):
        print(img["fingerprint"])
' "$NAME" "$PLATFORM_ALIAS" <<< "$image_json")

while read -r fp; do
  [[ -n "$fp" ]] || continue
  incus image delete "$fp" --project "$CACHE_PROJECT"
done <<< "$old_fps"

incus image import \
  "$META"/tarball/*.tar.xz \
  "$ROOTFS"/*.squashfs \
  --project "$CACHE_PROJECT" \
  --alias "$NAME" \
  --alias "$PLATFORM_ALIAS"

echo "Imported into project '$CACHE_PROJECT' as:"
echo "  $NAME"
echo "  $PLATFORM_ALIAS"
