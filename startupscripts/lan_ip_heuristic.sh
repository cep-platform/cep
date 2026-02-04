ip -4 addr | grep -oP "$(traceroute -n google.com | sed -n '2p' | grep -Eo '([0-9]{1,3}\.){2}[0-9]{1,3}')\.(2[0-4]\d|25[0-4]|1\d\d|[2-9]\d?)"
