# Pydio-cells

![Pydio-cells](https://raw.githubusercontent.com/linuxserver/docker-templates/master/linuxserver.io/img/pydio-cells-icon.png)

[Pydio-cells](https://pydio.com/) is the nextgen file sharing platform for organizations. It is a full rewrite of the Pydio project using the Go language following a micro-service architecture.

## Application setup

You must first create a mysql database for Pydio Cells. Using our [mariadb image](https://hub.docker.com/r/linuxserver/mariadb) is recommended.

Then access the web gui setup wizard at `https://SERVER_IP:8080` if accessing locally (must set `SERVER_IP` env var), or at `https://pydio-cells.domain.com` if reverse proxying.

Image: `ghcr.io/linuxserver-playground/pydio-cells:latest` ([https://github.com/linuxserver-playground/docker-pydio-cells](https://github.com/linuxserver-playground/docker-pydio-cells))
