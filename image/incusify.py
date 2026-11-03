#!/usr/bin/env python3
"""Convert a materialized OCI image layout into the two tarballs that
``incus image import`` needs for an OCI-style ("application container") image:

    metadata.tar  (metadata.yaml + config.json)
    rootfs.tar    (all layers merged)

This mirrors what incus-compose itself does for images it builds and pulls:

- ``metadata.yaml`` carries the incus image metadata plus a ``type: oci``
  property (this is what makes incusd treat instances of the image as
  application containers: the instance inherits ``image.type: oci``, which
  makes incusd unpack the metadata tarball's ``config.json`` to the instance
  dir and honor ``oci.entrypoint``/``oci.cwd``), and the ``oci.*`` properties
  incus-compose reads back when creating instances.
- ``config.json`` is an OCI *runtime* spec; incusd reads
  ``Process.{Args,Env,Cwd,User}`` out of it and runs them as the init.

Usage: incusify.py <oci-layout-dir> <out-dir>

Determinism: identical inputs produce identical tarballs (fixed timestamps,
sorted entries), so re-importing an unchanged build hits the same fingerprint.
"""
from __future__ import annotations

import io
import json
import os
import stat
import sys
import tarfile

# Fixed creation date (2000-01-01) so the metadata tarball - and therefore the
# incus fingerprint - only changes when the image content does. incusd
# requires a non-zero creation date.
CREATION_DATE = 946684800

# Registry architecture spelling -> incus architecture name.
INCUS_ARCH = {"amd64": "x86_64", "arm64": "aarch64"}


def read_blob(blobs_dir: str, digest: str) -> dict:
    with open(os.path.join(blobs_dir, digest.split(":", 1)[1]), "rb") as f:
        return json.load(f)


def image_refs(layout: str) -> tuple[dict, dict]:
    """Return (manifest, image-config) for the single image in the layout."""
    blobs_dir = os.path.join(layout, "blobs", "sha256")
    index = json.load(open(os.path.join(layout, "index.json")))["manifests"][0]
    manifest = read_blob(blobs_dir, index["digest"])
    config = read_blob(blobs_dir, manifest["config"]["digest"])
    return manifest, config


def merge_layers(layout: str, manifest: dict, out_tar: str) -> None:
    """Unpack every layer tar (in manifest order) and write one rootfs.tar."""
    blobs_dir = os.path.join(layout, "blobs", "sha256")
    merged = os.path.join(layout, ".merged")

    # Start from a clean slate so a re-run on the same layout cannot leak
    # entries from a previous image.
    import shutil
    shutil.rmtree(merged, ignore_errors=True)
    os.makedirs(merged, exist_ok=True)

    for layer in manifest["layers"]:
        digest = layer["digest"].split(":", 1)[1]
        # skopeo writes gzip-compressed layer blobs for oci: layouts
        # (mediaType ...tar+gzip), so auto-detect the compression.
        with tarfile.open(os.path.join(blobs_dir, digest), "r:*") as tf:
            # The layers come from our own nix2container image: entries are
            # absolute /nix/store/... paths. The 'tar' filter strips the
            # leading slash (making them relative to the merge dir) while
            # keeping modes/symlinks intact.
            tf.extractall(path=merged, filter="tar")

    with tarfile.open(out_tar, "w", format=tarfile.GNU_FORMAT) as tf:
        for name in sorted_entries(merged):
            path = os.path.join(merged, name)
            info = tarinfo_for(path, name)
            if info.isfile():
                with open(path, "rb") as f:
                    tf.addfile(info, f)
            else:
                tf.addfile(info)


def sorted_entries(root: str) -> list[str]:
    """All paths under root, relative, sorted for a reproducible tarball."""
    names = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        rel_dir = os.path.relpath(dirpath, root)
        prefix = "" if rel_dir == "." else rel_dir + os.sep
        for entry in dirnames + filenames:
            names.append(prefix + entry)
    return sorted(names)


def tarinfo_for(path: str, name: str) -> tarfile.TarInfo:
    """A TarInfo for <path> (entry <name>) with reproducible metadata."""
    st = os.lstat(path)
    info = tarfile.TarInfo("./" + name)
    info.mode = stat.S_IMODE(st.st_mode)
    info.mtime = 0
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""

    if stat.S_ISLNK(st.st_mode):
        info.type = tarfile.SYMTYPE
        info.linkname = os.readlink(path)
        info.size = 0
    elif stat.S_ISDIR(st.st_mode):
        info.type = tarfile.DIRTYPE
        info.size = 0
    elif stat.S_ISREG(st.st_mode):
        info.type = tarfile.REGTYPE
        info.size = st.st_size
    else:
        raise ValueError(f"unsupported file type: {path}")

    return info


def write_metadata_tar(image_config: dict, index_platform: dict, out_tar: str) -> None:
    """Write metadata.tar: metadata.yaml + config.json (OCI runtime spec)."""
    entrypoint = image_config.get("Entrypoint") or []
    cmd = image_config.get("Cmd") or []
    env = image_config.get("Env") or []
    cwd = image_config.get("WorkingDir") or "/"
    arch = INCUS_ARCH.get(index_platform.get("architecture", "amd64"), "amd64")

    runtime_spec = {
        "ociVersion": "1.0.0",
        "process": {
            "args": entrypoint + cmd,
            "env": env,
            "cwd": cwd,
            "user": {"uid": 0, "gid": 0, "additionalGids": [0]},
        },
    }

    # The properties incus-compose reads back from the image (see
    # ociReadProperties in lxc/incus-compose client/resource_image_oci.go):
    # a compose `command:` is appended to oci.entrypoint at instance
    # creation; oci.volumes doubles as the "config already stored" marker.
    metadata = {
        "architecture": arch,
        "creation_date": CREATION_DATE,
        "properties": {
            "description": "localhost/cep:latest (nix-built OCI)",
            "architecture": arch,
            "type": "oci",
            "oci.uid": "0",
            "oci.gid": "0",
            "oci.entrypoint": " ".join(entrypoint),
            "oci.cmd": " ".join(cmd),
            "oci.cwd": cwd,
            "oci.volumes": ",",
        },
    }

    def add(tf: tarfile.TarFile, name: str, data: bytes) -> None:
        info = tarfile.TarInfo(name)
        info.size = len(data)
        info.mode = 0o644
        info.mtime = 0
        info.uid = 0
        info.gid = 0
        tf.addfile(info, io.BytesIO(data))

    with tarfile.open(out_tar, "w", format=tarfile.GNU_FORMAT) as tf:
        add(tf, "metadata.yaml", json.dumps(metadata, indent=2).encode())
        add(tf, "config.json", json.dumps(runtime_spec, indent=2).encode())


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit(f"usage: {sys.argv[0]} <oci-layout-dir> <out-dir>")
    layout, out_dir = sys.argv[1], sys.argv[2]
    os.makedirs(out_dir, exist_ok=True)

    manifest, config = image_refs(layout)
    merge_layers(layout, manifest, os.path.join(out_dir, "rootfs.tar"))
    index = json.load(open(os.path.join(layout, "index.json")))["manifests"][0]
    write_metadata_tar(config["config"], index.get("platform", {}), os.path.join(out_dir, "metadata.tar"))


if __name__ == "__main__":
    main()
