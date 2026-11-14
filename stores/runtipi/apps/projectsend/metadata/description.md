# Projectsend

![Projectsend](http://www.projectsend.org/wp-content/themes/projectsend/img/screenshots.png)

[Projectsend](http://www.projectsend.org) is a self-hosted application that lets you upload files and assign them to specific clients that you create yourself. Secure, private and easy. No more depending on external services or e-mail to send those files.

## Application setup

Requires a user and database in either mysql or mariadb.

crontab for scheduled tasks should be added to /config/crontabs/abc and the container restarted to enable.

To set PHP options like max upload size please edit /config/php/projectsend.ini

To use translations, follow the instructions [here](https://www.projectsend.org/how-to-use-translation-files/). The necessary paths are symlinked under `/config/translations` (note that the "templates" paths don't need `lang` subdirectories).

More info at [ProjectSend](http://www.projectsend.org).

Image: `ghcr.io/linuxserver-playground/projectsend:latest` ([https://github.com/linuxserver-playground/docker-projectsend](https://github.com/linuxserver-playground/docker-projectsend))
