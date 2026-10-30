{ pkgs, ... }:
{
    virtualisation.incus.enable = true;
    virtualisation.incus.ui.enable = true;
    networking.nftables.enable = true;
    users.users.sven.extraGroups = ["incus-admin"];

    virtualisation.incus.preseed = {
        # incus-compose copies images between its cache project and compose
        # projects in pull mode, and incusd dials the source over the network
        # even when it is itself - so the daemon must listen on TCP. 8443 is
        # the incus port; the cep-caddy https port was moved off 8443 in
        # compose.yml for the same reason.
        config = {
            "core.https_address" = ":8443";
        };

        networks = [
        {
            config = {
                "ipv4.address" = "10.0.100.1/24";
                "ipv4.nat" = "true";
            };
            name = "incusbr0";
            type = "bridge";
        }
        ];
        profiles = [
        {
            devices = {
                eth0 = {
                    name = "eth0";
                    network = "incusbr0";
                    type = "nic";
                };
                root = {
                    path = "/";
                    pool = "default";
                    size = "35GiB";
                    type = "disk";
                };
            };
            name = "default";
        }
        ];
        storage_pools = [
        {
            config = {
                source = "/var/lib/incus/storage-pools/default";
            };
            driver = "dir";
            name = "default";
        }
        ];
    };

}
