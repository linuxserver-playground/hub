# Piwigo

![Piwigo](https://raw.githubusercontent.com/linuxserver/docker-templates/master/linuxserver.io/img/piwigo-banner.png)

[Piwigo](http://piwigo.org/) is a photo gallery software for the web that comes with powerful features to publish and manage your collection of pictures.

## Application setup

* You must create a user and database for piwigo to use in a mysql/mariadb server.

* Self-signed keys are generated the first time you run the container and can be found in `/config/keys`, if needed, you can replace them with your own.

* The easiest way to edit the configuration file is to enable local files editor from the plugins page and use it to configure email settings etc."

Image: `ghcr.io/linuxserver-playground/piwigo:latest` ([https://github.com/linuxserver-playground/docker-piwigo](https://github.com/linuxserver-playground/docker-piwigo))
