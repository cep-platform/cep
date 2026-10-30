#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

# Build the cep image with nix (nix2container - no docker/podman/buildah on the
# host), convert it to the split format `incus image import` wants and put it
# in the incus-compose image cache. After this, `incus-compose up` resolves
# the compose file's `image: localhost/cep:latest` from the cache.
#
# Why not `incus-compose build`? Its nix2container builder (PR #230) is only
# on the incus-compose develop branch, unreleased as of 1.3.5. This script
# does the same import by hand; switching to `incus-compose --profile build
# build cep-build` becomes possible once a release carries that PR.

# 1. Evaluate the image descriptor and the skopeo that can read it.
IMAGE=$(nix build .#cep-image --print-out-paths)
SKOPEO=$(nix build '.#skopeo-nix2container^out' --print-out-paths)

# 2. Materialize the image as an OCI layout (skopeo's nix: transport).
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
"$SKOPEO/bin/skopeo" --insecure-policy copy "nix:$IMAGE" "oci:$WORK/oci"

# 3. Convert to the incus split image: metadata.tar + rootfs.tar.
python3 incusify.py "$WORK/oci" "$WORK/out"
ls -lh "$WORK/out"

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

# 4. Drop any previous cep import first: nix builds are deterministic, so an
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

# 5. Import. This is what makes the image an OCI-style "application container"
# image: metadata.yaml carries `type: oci` + the `oci.*` properties, and
# config.json carries the OCI runtime spec (Entrypoint = cep) - see
# incusify.py.
incus image import \
  "$WORK/out/metadata.tar" \
  "$WORK/out/rootfs.tar" \
  --project "$CACHE_PROJECT" \
  --alias "$NAME" \
  --alias "$PLATFORM_ALIAS"

echo "Imported into project '$CACHE_PROJECT' as:"
echo "  $NAME"
echo "  $PLATFORM_ALIAS"
