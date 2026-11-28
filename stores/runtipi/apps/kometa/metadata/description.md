# Kometa

![Kometa](https://raw.githubusercontent.com/linuxserver/docker-templates/master/linuxserver.io/img/kometa-banner.png)

[Kometa](https://github.com/Kometa-Team/Kometa) is a powerful tool designed to give you complete control over your media libraries. With Kometa, you can take your customization to the next level, with granular control over metadata, collections, overlays, and much more.

## Application setup

There is a [walkthrough](https://kometa.wiki/en/latest/kometa/install/docker/#setting-up-the-initial-config-file) available to help get you up and running.

This image supports all of the environment variables listed [here](https://kometa.wiki/en/latest/kometa/environmental/) and all commandline arguments.

To perform a one-time run use `docker run` (or `docker compose run`) with the `--rm`, and `-e KOMETA_RUN=True` or `--run` arguments. This will cause the container to process your config immediately instead of waiting for the scheduled time, and delete the old container after completion.

For more information see the [official wiki](https://kometa.wiki).

Image: `ghcr.io/linuxserver-playground/kometa:latest` ([https://github.com/linuxserver-playground/docker-kometa](https://github.com/linuxserver-playground/docker-kometa))
