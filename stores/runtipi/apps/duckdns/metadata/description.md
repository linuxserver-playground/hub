# Duckdns

![Duckdns](https://raw.githubusercontent.com/linuxserver/docker-templates/master/linuxserver.io/img/duckdns.png)

[Duckdns](https://duckdns.org/) is a free service which will point a DNS (sub domains of duckdns.org) to an IP of your choice. The service is completely free, and doesn't require reactivation or forum posts to maintain its existence.

## Application setup

- Go to the [duckdns website](https://duckdns.org/), register your subdomain(s) and retrieve your token.
- Create a container with your subdomain(s) and token. If you own `user.duckdns.org`, you set `SUBDOMAINS=user`. You would NOT set a sub subdomain like `overseerr` from `overseerr.user.ducksdns.org`.
- It will update your IP with the DuckDNS service every 5 minutes (with a random jitter).

## Notice regarding automatic detection

Using the `UPDATE_IP` variable whatever its value (`ipv4`, `ipv6` or `both`) uses external *Cloudflare whoami* service to detect public IP addresses.
**Be aware that using this variable will query a third-party service other than DuckDNS.**

Omitting the `UPDATE_IP` variable uses DuckDNS for detection and only supports IPv4.

Image: `ghcr.io/linuxserver-playground/duckdns:latest` ([https://github.com/linuxserver-playground/docker-duckdns](https://github.com/linuxserver-playground/docker-duckdns))
