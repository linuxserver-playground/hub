# Resilio-sync

![Resilio-sync](https://raw.githubusercontent.com/linuxserver/docker-templates/master/linuxserver.io/img/resilio-sync-logo.png)

[Resilio-sync](https://www.resilio.com/individuals/) (formerly BitTorrent Sync) uses the BitTorrent protocol to sync files and folders between all of your devices. There are both free and paid versions, this container supports both. There is an official sync image but we created this one as it supports user mapping to simplify permissions for volumes.

## Application setup

* Webui is at `<your-ip>:8888`, for account creation and configuration.
* More info on setup at [Resilio Sync](https://www.resilio.com/individuals/)

Image: `ghcr.io/linuxserver-playground/resilio-sync:latest` ([https://github.com/linuxserver-playground/docker-resilio-sync](https://github.com/linuxserver-playground/docker-resilio-sync))
