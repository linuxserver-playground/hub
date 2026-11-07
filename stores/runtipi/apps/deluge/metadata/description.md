# Deluge

![Deluge](https://raw.githubusercontent.com/linuxserver/docker-templates/master/linuxserver.io/img/deluge-logo.png)

[Deluge](http://deluge-torrent.org/) is a lightweight, Free Software, cross-platform BitTorrent client.

* Full Encryption
* WebUI
* Plugin System
* Much more...

## Application setup

The admin interface is available at `http://SERVER-IP:8112` with a default user/password of admin/deluge.

To change the password (recommended) log in to the web interface and go to Preferences->Interface->Password.

Change the inbound port to 6881 (or whichever port you've mapped for the container) under Preferences->Network, otherwise random ports will be used.

Image: `ghcr.io/linuxserver-playground/deluge:latest` ([https://github.com/linuxserver-playground/docker-deluge](https://github.com/linuxserver-playground/docker-deluge))
