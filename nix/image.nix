# Cep OCI image, built with nix2container for incus-compose's `nix2container`
# builder (see docs/plans/incus-nix-image.md).
#
# Incus runs OCI images as application containers: the image Entrypoint is
# PID 1 (Incus maps `oci.entrypoint` -> `lxc.init.cmd`) and systemd never
# boots. So this is a distroless-style image, not a NixOS system container:
# the rootfs is /nix/store closures plus the /bin and /app trees built below.
#
# Everything evaluates against the flake's nixos-25.11 nixpkgs input; commit
# nix/flake.lock so builds are pinned.
{ self, pkgs, nix2container }:

let
  py = pkgs.python313Packages;

  # incus-compose is not in nixpkgs: use the official static release binary
  # (built with CGO_ENABLED=0). The appstore backend shells out to it
  # (src/cep/apps/incus.py).
  incus-compose = pkgs.stdenv.mkDerivation {
    pname = "incus-compose";
    version = "1.3.5";
    src = pkgs.fetchurl {
      url = "https://github.com/lxc/incus-compose/releases/download/v1.3.5/incus-compose_1.3.5_linux_amd64.tar.gz";
      sha256 = "0ed925b152ec5cea08b72f2f2ffbaa167619103a9aefb2582285920d5931facb";
    };
    dontConfigure = true;
    dontBuild = true;
    installPhase = ''
      runHook preInstall
      install -Dm 0755 incus-compose $out/bin/incus-compose
      runHook postInstall
    '';
  };

  # The cep package itself. Dependencies come from the flake's nixpkgs input
  # (nixos-25.11), not from uv.lock; buildPythonApplication does not enforce
  # the pyproject minimums, so if these lag behind pyproject.toml and the
  # smoke tests still pass (nix build ./nix#cep && ./result/bin/cep --help),
  # the pins are advisory. Switch to uv2nix if real divergence shows up.
  cep = py.buildPythonApplication rec {
    pname = "cep";
    version = "0.1.0";
    pyproject = true;
    # self = the flake source: the whole git tree (gitignored files excluded).
    src = self;
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
      # cli/server.py starts uvicorn with reload=True (dev-only flag) and
      # reload requires watchfiles.
      #TODO: make reload env-driven, then drop this from the image
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
    install -m 0755 ${self}/startupscripts/start_client.sh $out/app/start.sh
    install -m 0644 ${self}/startupscripts/client_banner.txt $out/app/client_banner.txt
  '';
in
{
  image = nix2container.buildImage {
    name = "localhost/cep";
    tag = "latest";
    # Spread the copyToRoot closures over layers by popularity so a cep-only
    # change does not repush the (large, stable) Python closure.
    maxLayers = 10;

    copyToRoot = [ root runtime-tree ];

    # OCI image config keys are serialized verbatim - keep them capitalized.
    config = {
      Entrypoint = [ "${cep}/bin/cep" ];
      WorkingDir = "/app";
      Env = [
        "HOME=/root"
        "PATH=/bin"
        "PYTHONDONTWRITEBYTECODE=1"
        "PYTHONUNBUFFERED=1"
      ];
    };
  };

  inherit cep;
}