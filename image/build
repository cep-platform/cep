#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

# Build the cep image with nix and import it into the incus-compose image
# cache, so `incus-compose up` resolves `image: localhost/cep:latest`.
# By hand because incus-compose has no released nix2container builder yet
# (lxc/incus-compose PR #230 is develop-branch only as of 1.3.5).

# Evaluate the image descriptor and the skopeo that can read it.
IMAGE=$(nix build .#cep-image --print-out-paths)
SKOPEO=$(nix build '.#skopeo-nix2container^out' --print-out-paths)

# Materialize the image as an OCI layout (skopeo's nix: transport).
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
"$SKOPEO/bin/skopeo" --insecure-policy copy "nix:$IMAGE" "oci:$WORK/oci"

# Convert to the incus split image: metadata.tar + rootfs.tar.
python3 incusify.py "$WORK/oci" "$WORK/out"
ls -lh "$WORK/out"

CACHE_PROJECT=incus-compose-cache

# incus-compose maps the compose file's `image: localhost/cep:latest`
# to the incus image name `local/cep:latest`
NAME=local/cep:latest
PLATFORM_ALIAS=local/cep:latest/amd64

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
  "$WORK/out/metadata.tar" \
  "$WORK/out/rootfs.tar" \
  --project "$CACHE_PROJECT" \
  --alias "$NAME" \
  --alias "$PLATFORM_ALIAS"

echo "Imported into project '$CACHE_PROJECT' as:"
echo "  $NAME"
echo "  $PLATFORM_ALIAS"
