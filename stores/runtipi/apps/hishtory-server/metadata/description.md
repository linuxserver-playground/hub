# Hishtory-server

![Hishtory-server](https://raw.githubusercontent.com/linuxserver/docker-templates/master/linuxserver.io/img/hishtory-server-icon.png)

[hiSHtory](https://github.com/ddworken/hishtory) is a better shell history. It stores your shell history in context (what directory you ran the command in, whether it succeeded or failed, how long it took, etc). This is all stored locally and end-to-end encrypted for syncing to to all your other computers.

## Application setup

After you have installed hishtory on your machine, add `export HISHTORY_SERVER=http://127.0.0.1:8080` (with your server details) to your shellrc. Then run `hishtory init` (or `hishtory init ${SECRET_KEY}`) to initialise hishtory against your local server.

See the [project readme](https://github.com/ddworken/hishtory/blob/master/README.md) for more details.

Image: `ghcr.io/linuxserver-playground/hishtory-server:latest` ([https://github.com/linuxserver-playground/docker-hishtory-server](https://github.com/linuxserver-playground/docker-hishtory-server))
