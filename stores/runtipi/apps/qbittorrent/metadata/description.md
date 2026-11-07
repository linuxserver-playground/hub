# Qbittorrent

![Qbittorrent](https://github.com/linuxserver/docker-templates/raw/master/linuxserver.io/img/qbittorrent-icon.png)

The [Qbittorrent](https://www.qbittorrent.org/) is a bittorrent client programmed in C++ / Qt that uses libtorrent (sometimes called libtorrent-rasterbar) by Arvid Norberg.

## Application setup

The web UI is at `<your-ip>:8080` and a temporary password for the `admin` user will be printed to the container log on startup.

You must then change username/password in the web UI section of settings. If you do not change the password a new one will be generated every time the container starts.

If you are running a very old (3.x) kernel you may run into [this issue](https://github.com/linuxserver/docker-qbittorrent/issues/103) which can be worked around using [this method](https://github.com/linuxserver/docker-qbittorrent/issues/103#issuecomment-831238484)

### WEBUI_PORT variable

Due to issues with CSRF and port mapping, should you require to alter the port for the web UI you need to change both sides of the -p 8080 switch AND set the WEBUI_PORT variable to the new port.

For example, to set the port to 8123 you need to set -p 8123:8123 and -e WEBUI_PORT=8123

### TORRENTING_PORT

A bittorrent client can be an active or a passive node. Running your client as an active node has the advantage of being able to connect to both active and passive peers, and can potentially increase the number of incoming connections. This requires an open port on the host machine which might differ from container's internal one.

Similarly to the WEBUI_PORT, to set the port to 6887 you need to pass -p 6887:6887, -p 6887:6887/udp and -e TORRENTING_PORT=6887 arguments to Docker.

Image: `ghcr.io/linuxserver-playground/qbittorrent:latest` ([https://github.com/linuxserver-playground/docker-qbittorrent](https://github.com/linuxserver-playground/docker-qbittorrent))
