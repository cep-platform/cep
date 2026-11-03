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

  # The cep package itself. Version comes from pyproject.toml (single source
  # of truth). Dependencies come from the flake's nixpkgs input (nixos-26.05),
  # not from uv.lock; buildPythonApplication neither enforces the pyproject
  # minimums nor resolves extras, so uvicorn/httpx are listed explicitly and
  # watchfiles is included for cli/server.py's dev-only uvicorn reload.
  #TODO: investigate the nixpkgs <-> uv interplay; switch to uv2nix if the
  # two dependency sets diverge
  cep = py.buildPythonApplication rec {
    pname = "cep";
    version = (builtins.fromTOML (builtins.readFile "${repoRoot}/pyproject.toml")).project.version;
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

  # Non-package trees: working dirs and the startup script. Store paths are
  # 0555, so create the runtime-writable dirs with 0755.
  #TODO: this wiring only exists because dependencies are managed through
  # nix; managing everything with uv may be simpler for dev. Revisit when
  # this becomes a flashable/immutable image.
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

  # Distroless rootfs has no /etc/ssl: the image has to roll it by hand.
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
