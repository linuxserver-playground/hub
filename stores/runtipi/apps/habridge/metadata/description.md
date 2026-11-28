# Habridge

![Habridge](https://raw.githubusercontent.com/linuxserver/docker-templates/master/linuxserver.io/img/habridge-logo.png)

[Habridge](https://github.com/bwssytems/ha-bridge/) emulates Philips Hue API to other home automation gateways such as an Amazon Echo/Dot Gen 1 (gen 2 has issues discovering ha-bridge) or other systems that support Philips Hue. The Bridge handles basic commands such as On, Off and brightness commands of the hue protocol. This bridge can control most devices that have a distinct API.

## Application setup

To set up the ha-bridge simply go to http://localhost:8080. Once you are in the webui you can add devices and configure ha-bridge to your liking.

For information on how to configure ha-bridge, go to their wiki at [https://github.com/bwssytems/ha-bridge/wiki](https://github.com/bwssytems/ha-bridge/wiki)

Image: `ghcr.io/linuxserver-playground/habridge:latest` ([https://github.com/linuxserver-playground/docker-habridge](https://github.com/linuxserver-playground/docker-habridge))
