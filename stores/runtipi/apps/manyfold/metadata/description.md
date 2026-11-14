# Manyfold

![Manyfold](https://raw.githubusercontent.com/linuxserver/docker-templates/master/linuxserver.io/img/manyfold-logo.png)

[Manyfold](https://github.com/manyfold3d/manyfold/)  is an open source, self-hosted web application for managing a collection of 3D models, particularly focused on 3D printing.

## Application setup

This container *requires* a separate Redis/Valkey instance to run. Sqlite is supported but we recommend an external Postgres or MariaDB database for better performance.

To generate keys for `SECRET_KEY_BASE` you can run `docker run --rm -it --entrypoint /bin/bash lscr.io/linuxserver/manyfold:latest generate-secret`.

You don't have to use `/libraries` and you're not limited to a single path, you can mount as many arbitrary paths as you like as long as you make sure the permissions match the user running the container.

For more information check out the [Manyfold documentation](https://manyfold.app/get-started/).

Image: `ghcr.io/linuxserver-playground/manyfold:latest` ([https://github.com/linuxserver-playground/docker-manyfold](https://github.com/linuxserver-playground/docker-manyfold))
