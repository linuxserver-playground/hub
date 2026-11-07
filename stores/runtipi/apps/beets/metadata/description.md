# Beets

![Beets](https://raw.githubusercontent.com/linuxserver/docker-templates/master/linuxserver.io/img/beets-icon.png)

[Beets](http://beets.io/) is a music library manager and not, for the most part, a music player. It does include a simple player plugin and an experimental Web-based player, but it generally leaves actual sound-reproduction to specialized tools.

## Application setup

Edit the config file in /config

To edit the config from within the container use `beet config -e`

For a command prompt as user abc `docker exec -it -u abc beets bash`

See [Beets](http://beets.io/) for more info.

Contains [beets-extrafiles](https://github.com/Holzhaus/beets-extrafiles) plugin, [configuration details](https://github.com/Holzhaus/beets-extrafiles#usage)

Image: `ghcr.io/linuxserver-playground/beets:latest` ([https://github.com/linuxserver-playground/docker-beets](https://github.com/linuxserver-playground/docker-beets))
