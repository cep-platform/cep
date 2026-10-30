{ ... }:
{
    # 8443: the incus daemon's core.https_address (see modules/incus.nix);
    # the appstore container registers its remote against it.
    networking.firewall.allowedTCPPorts = [ 80 443 8443 ];
    networking.firewall.trustedInterfaces = [
        "incusbr0"
    ];
    networking.firewall.allowedUDPPorts = [ 53 4242 51820 ];
}
