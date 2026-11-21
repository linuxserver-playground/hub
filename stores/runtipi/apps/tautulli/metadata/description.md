# Tautulli

![Tautulli](https://raw.githubusercontent.com/linuxserver/docker-templates/master/linuxserver.io/img/tautulli-icon.png)

[Tautulli](http://tautulli.com) is a python based web application for monitoring, analytics and notifications for Plex Media Server.

## Application setup

Access the webui at `<your-ip>:8181`, for more information check out [Tautulli](http://tautulli.com).
To use the built-in Plex LogViewer you have to add a volume, preferably Read-Only. Then in Tautulli gui settings, under `Plex Media Server`, turn on `Show Advanced` and set the `Logs Folder` to the folder you mapped.

Image: `ghcr.io/linuxserver-playground/tautulli:latest` ([https://github.com/linuxserver-playground/docker-tautulli](https://github.com/linuxserver-playground/docker-tautulli))
