# Synclounge

![Synclounge](https://raw.githubusercontent.com/linuxserver/docker-templates/master/linuxserver.io/img/synclounge-banner.png)

[Synclounge](https://github.com/samcm/synclounge) is a third party tool that allows you to watch Plex in sync with your friends/family, wherever you are.

## Application setup

The web app and the server are both accessible at `http://SERVERIP:8088`.

Note: It is recommended to use `http` as the external proto with a reverse proxy due to `https` not working with external plex clients.

Image: `ghcr.io/linuxserver-playground/synclounge:latest` ([https://github.com/linuxserver-playground/docker-synclounge](https://github.com/linuxserver-playground/docker-synclounge))
