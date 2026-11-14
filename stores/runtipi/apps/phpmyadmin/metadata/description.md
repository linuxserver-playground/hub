# Phpmyadmin

![Phpmyadmin](https://raw.githubusercontent.com/linuxserver/docker-templates/master/linuxserver.io/img/phpmyadmin-logo.png)

[Phpmyadmin](https://github.com/phpmyadmin/phpmyadmin/) is a free software tool written in PHP, intended to handle the administration of MySQL over the Web. phpMyAdmin supports a wide range of operations on MySQL and MariaDB.

## Application setup

This image uses nginx, in contrast to the official images which offer fpm-only or Apache variants.

We support all of the official [environment variables](https://docs.phpmyadmin.net/en/latest/setup.html#docker-environment-variables) for configuration as well as directly editing the config files.

For more information check out the [phpmyadmin documentation](https://www.phpmyadmin.net/docs/).

Image: `ghcr.io/linuxserver-playground/phpmyadmin:latest` ([https://github.com/linuxserver-playground/docker-phpmyadmin](https://github.com/linuxserver-playground/docker-phpmyadmin))
