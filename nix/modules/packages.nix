{ pkgs, ... }:
{
    environment.systemPackages = with pkgs; [
        gcc
        curl
        wget
        tmux
	python3
	uv
    btrfs-progs
    ];
}
