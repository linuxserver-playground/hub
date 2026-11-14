# Mstream

![Mstream](https://raw.githubusercontent.com/linuxserver/docker-templates/master/linuxserver.io/img/mstream-icon.png)

[mstream](https://mstream.io/) is a personal music streaming server. You can use mStream to stream your music from your home computer to any device, anywhere.  There are mobile apps available for both Android and iPhone.

## Application setup

Access the webui at `http://<your-ip>:3000`

Settings are adjusted through the web ui or via editing of `config.json`. For more information check out [Mstream](https://github.com/IrosTheBeggar/mStream/blob/master/docs/json_config.md#json-config).

## IMPORTANT NOTICE:
mStream v5 no longer accepts cli arguments for setting the user and password and requires the use of `config.json`. Therefore, the environment variables `USER`, `PASSWORD` and `USE_JSON` are deprecated.

v4's `config.json` is not compatible with v5. Existing `config.json` will be renamed to `config.json.v4-bak` for your reference and a new default `config.json` will be created upon upgrade from v4 to v5.

Image: `ghcr.io/linuxserver-playground/mstream:latest` ([https://github.com/linuxserver-playground/docker-mstream](https://github.com/linuxserver-playground/docker-mstream))
