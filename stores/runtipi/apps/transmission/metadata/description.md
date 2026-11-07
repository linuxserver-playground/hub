# Transmission

![Transmission](https://raw.githubusercontent.com/linuxserver/docker-templates/master/linuxserver.io/img/transmission.png)

[Transmission](https://www.transmissionbt.com/) is designed for easy, powerful use. Transmission has the features you want from a BitTorrent client: encryption, a web interface, peer exchange, magnet links, DHT, µTP, UPnP and NAT-PMP port forwarding, webseed support, watch directories, tracker editing, global and per-torrent speed limits, and more.

## Application setup

Webui is on port 9091, the settings.json file in /config has extra settings not available in the webui. Stop the container before editing it or any changes won't be saved.

## Securing the webui with a username/password.

Use the `USER` and `PASS` variables in docker run/create/compose to set authentication. Do not manually edit the `settings.json` to input user/pass, otherwise transmission cannot be stopped cleanly by the s6 supervisor.

## Updating Blocklists Automatically

This requires `"blocklist-enabled": true,` to be set. By setting this to true, it is assumed you have also populated `blocklist-url` with a valid block list.

The automatic update is a shell script that downloads a blocklist from the url stored in the settings.json, gunzips it, and restarts the transmission daemon.

The automatic update will run once a day at 3am local server time.

## Using whitelist

Use `WHITELIST` to enable a list of ip as whitelist. This enable support for `rpc-whitelist`. When `WHITELIST` is empty support for whitelist is disabled.

Use `HOST_WHITELIST` to enable an list of dns names as host-whitelist. This enable support for `rpc-host-whitelist`. When `HOST_WHITELIST` is empty support for host-whitelist is disabled.

## Use alternative Transmission torrent ports

Use `PEERPORT` to specify the port(s) Transmission should listen on.  This disables random port selection.  This should be the same as the port mapped in your docker configuration.

Image: `ghcr.io/linuxserver-playground/transmission:latest` ([https://github.com/linuxserver-playground/docker-transmission](https://github.com/linuxserver-playground/docker-transmission))
