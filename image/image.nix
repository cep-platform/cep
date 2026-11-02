# Cep OCI image, built with nix2container (see docs/plans/incus-nix-image.md).
#
# Incus runs OCI images as application containers: the image Entrypoint is
# PID 1 (Incus maps `oci.entrypoint` -> `lxc.init.cmd`) and systemd never
# boots. So this is a distroless-style image, not a NixOS system container:
# the rootfs is /nix/store closures plus the /bin and /app trees built below.
#
# Everything evaluates against the flake's nixos-26.05 nixpkgs input; commit
# image/flake.lock so builds are pinned.
#
# Import into Incus happens in image/build.sh: incus-compose has no released
# nix2container builder yet (lxc/incus-compose PR #230 lives on the develop
# branch only), so build.sh materializes this image and imports it with
# `incus image import` under the aliases incus-compose looks up.
#
# repoRoot: the repository root (flake lives in a git subdirectory, and
# nix >= 2.28's subdir-flake semantics make `self` the subtree only).
{ repoRoot, pkgs, nix2container }:

let
  py = pkgs.python313Packages;

  # incus-compose is not in nixpkgs: use the official static release binary
  # (built with CGO_ENABLED=0). The appstore backend shells out to it
  # (src/cep/apps/incus.py) from inside the cep-appstore container.
  incus-compose = pkgs.stdenv.mkDerivation {
    pname = "incus-compose";
    version = "1.3.5";
    src = pkgs.fetchurl {
      url = "https://github.com/lxc/incus-compose/releases/download/v1.3.5/incus-compose_1.3.5_linux_amd64.tar.gz";
      sha256 = "0ed925b152ec5cea08b72f2f2ffbaa167619103a9aefb2582285920d5931facb";
    };
    # The release tarball is flat (no directory entries), which trips
    # unpackPhase's sourceRoot auto-detection - unpack it by hand.
    dontUnpack = true;
    nativeBuildInputs = [ pkgs.gnutar ];
    installPhase = ''
      runHook preInstall
      tar -xzf "$src" incus-compose
      install -Dm 0755 incus-compose $out/bin/incus-compose
      runHook postInstall
    '';
  };

  # The cep package itself. Dependencies come from the flake's nixpkgs input
  # (nixos-26.05), not from uv.lock; buildPythonApplication does not enforce
  # the pyproject minimums, so if these lag behind pyproject.toml and the
  # smoke tests still pass (nix build ./image#cep && ./result/bin/cep --help),
  # the pins are advisory. Switch to uv2nix if real divergence shows up.
  #
  # fastapi[standard] in pyproject.toml pulls uvicorn/httpx as extras;
  # buildPythonApplication does not resolve extras, so list them explicitly.
  # watchfiles: cli/server.py starts uvicorn with reload=True (dev-only flag)
  # and reload requires it.
  cep = py.buildPythonApplication rec {
    pname = "cep";
    version = "0.1.0";
    pyproject = true;
    # The whole tracked git tree. Uncommitted files are invisible to the
    # build - `git add` new files before rebuilding.
    src = repoRoot;
    build-system = [ py.setuptools ];
    dependencies = with py; [
      fastapi
      httpx
      platformdirs
      psutil
      pydantic
      python-dotenv
      pyyaml
      requests
      result
      rich
      typer
      uvicorn
      #TODO: make cli/server.py's uvicorn reload env-driven, then drop
      # watchfiles from the image
      watchfiles
    ];
  };

  # Binaries exposed at /bin/ (symlinked, so files are not duplicated outside
  # /nix/store) so PATH finds them however Incus ends up setting it.
  root = pkgs.buildEnv {
    name = "cep-root";
    paths = [
      cep
      incus-compose
      pkgs.incus # appstore backend: `incus` CLI
      pkgs.nebula
      pkgs.iproute2 # `ip` in the CLI and startup scripts
      pkgs.traceroute # startupscripts/lan_ip_heuristic.sh
      pkgs.bash # provides /bin/sh for the startup scripts
      pkgs.coreutils
      pkgs.findutils
      pkgs.gnugrep
      pkgs.gnused

    # Lightweight development and debugging tools
      pkgs.curl
      pkgs.wget
      pkgs.bind # dig, nslookup, host
      pkgs.iputils # ping, arping
      pkgs.netcat-openbsd # nc
      pkgs.tcpdump
      pkgs.procps # ps, top, free, uptime
      pkgs.util-linux # lsblk, mount, dmesg, nsenter
      pkgs.file
      pkgs.which
      pkgs.less
      pkgs.jq
      pkgs.lsof
      pkgs.strace
      pkgs.gnupg
    ];
    pathsToLink = [ "/bin" ];
  };

  # Non-package trees: working dirs and the startup script. These need to be
  # writable at runtime - store paths are 0555, so create dirs with 0755
  # (container-root writes via DAC_OVERRIDE into 0555 store dirs would work,
  # but let's not rely on that).
  runtime-tree = pkgs.runCommand "cep-runtime-tree" { } ''
    install -d -m 0755 $out/app
    install -d -m 0755 $out/root/.cache/nebula
    install -d -m 0755 $out/root/.local/share/cep
    # cep.utils.get_executable_path() looks for nebula in ~/.cache/nebula;
    # symlinking there keeps utils.py unchanged (no download at build or run
    # time - replaces the old Dockerfile's download_nebula() build step).
    ln -s ${pkgs.nebula}/bin/nebula $out/root/.cache/nebula/nebula
    ln -s ${pkgs.nebula}/bin/nebula-cert $out/root/.cache/nebula/nebula-cert
    install -m 0755 ${repoRoot}/startupscripts/start_client.sh $out/app/start.sh
    install -m 0644 ${repoRoot}/startupscripts/client_banner.txt $out/app/client_banner.txt
  '';

  # Distroless rootfs has no /etc/ssl: the static pure-Go incus-compose
  # binary (CGO_ENABLED=0) reads the standard system cert paths, gets an
  # empty trust pool, and every HTTPS fetch fails with "x509: certificate
  # signed by unknown authority" (docker.io pulls; also curl/wget, whose
  # nixpkgs builds bake in the same default path). Materialize the nixpkgs
  # CA bundle at the standard path - NixOS hosts get this for free via
  # security.pki, the image has to roll it by hand.
  etc-ssl = pkgs.runCommand "cep-etc-ssl" { } ''
    install -d -m 0755 $out/etc/ssl/certs
    ln -s ${pkgs.cacert}/etc/ssl/certs/ca-bundle.crt $out/etc/ssl/certs/ca-certificates.crt
  '';
in
{
  image = nix2container.buildImage {
    name = "localhost/cep";
    tag = "latest";
    # Spread the copyToRoot closures over layers by popularity so a cep-only
    # change does not repush the (large, stable) Python closure.
    maxLayers = 10;

    copyToRoot = [ root runtime-tree etc-ssl ];

    # OCI image config keys are serialized verbatim - keep them capitalized.
    config = {
      Entrypoint = [ "${cep}/bin/cep" ];
      WorkingDir = "/app";
      Env = [
        "HOME=/root"
        "PATH=/bin"
        "PYTHONDONTWRITEBYTECODE=1"
        "PYTHONUNBUFFERED=1"
        # Belt-and-braces for tools that honor env over paths (openssl,
        # curl, wget, Go): the /etc/ssl symlink above already covers them.
        "SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt"
      ];
    };
  };

  inherit cep;
}
