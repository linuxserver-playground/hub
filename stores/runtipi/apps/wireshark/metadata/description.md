# Wireshark

![Wireshark](https://raw.githubusercontent.com/linuxserver/docker-templates/master/linuxserver.io/img/wireshark-icon.png)

[Wireshark](https://www.wireshark.org/) is the world’s foremost and widely-used network protocol analyzer. It lets you see what’s happening on your network at a microscopic level and is the de facto (and often de jure) standard across many commercial and non-profit enterprises, government agencies, and educational institutions. Wireshark development thrives thanks to the volunteer contributions of networking experts around the globe and is the continuation of a project started by Gerald Combs in 1998.

## Application setup

In order to dump from an interface you will need to pass `NET_ADMIN` at a minimum, optionally you can use host networking to capture from your host level device or specify a Docker network you want to capture from.

The application can be accessed at:

* https://yourhost:3001/

Image: `ghcr.io/linuxserver-playground/wireshark:latest` ([https://github.com/linuxserver-playground/docker-wireshark](https://github.com/linuxserver-playground/docker-wireshark))
