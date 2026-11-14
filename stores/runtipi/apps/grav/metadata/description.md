# Grav

![Grav](https://raw.githubusercontent.com/linuxserver/docker-templates/master/linuxserver.io/img/grav-logo.png)

[Grav](https://github.com/getgrav/grav/) is a Fast, Simple, and Flexible, file-based Web-platform.

## Application setup

For more information check out the [Grav documentation](https://learn.getgrav.org/). Our image includes the [grav-admin](https://github.com/getgrav/grav-plugin-admin) plugin.

To use the CLI tools you need to pass the working directory as part of your exec command (or use an interactive shell), e.g. `docker exec -it -w /app/www/public grav bin/gpm`

Image: `ghcr.io/linuxserver-playground/grav:latest` ([https://github.com/linuxserver-playground/docker-grav](https://github.com/linuxserver-playground/docker-grav))
