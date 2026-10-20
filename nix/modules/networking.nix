{ ... }:
{
    networking.firewall.allowedTCPPorts = [ 80 443 ];
    networking.firewall.trustedInterfaces = [
        "incusbr0"
    ];
    networking.firewall.allowedUDPPorts = [ 53 4242 51820 ];
}
