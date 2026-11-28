# Freshrss

![Freshrss](https://raw.githubusercontent.com/linuxserver/docker-templates/master/linuxserver.io/img/freshrss-banner.png)

[Freshrss](https://freshrss.org/) is a free, self-hostable aggregator for rss feeds.

## Application setup

Access the webui set up wizard at `http://serverIP:port`

For external databases, create a user and database in your mysql/mariadb server (not root) and then follow the setup wizard in the webui. Use the IP address for "host" of your database server.

Additional extensions can be dropped into `/config/www/freshrss/extensions` and will be active after container restart.

Image: `ghcr.io/linuxserver-playground/freshrss:latest` ([https://github.com/linuxserver-playground/docker-freshrss](https://github.com/linuxserver-playground/docker-freshrss))
