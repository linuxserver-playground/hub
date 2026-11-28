# Kavita

![Kavita](https://raw.githubusercontent.com/linuxserver/docker-templates/master/linuxserver.io/img/kavita-logo.png)

[Kavita](https://github.com/Kareadita/Kavita) is a fast, feature rich, cross platform reading server. Built with a focus for being a full solution for all your reading needs. Setup your own server and share your reading collection with your friends and family!

## Application setup

Access the webui at `<your-ip>:5000`. Follow the setup wizard on initial install.

The docker cli and compose yml samples provided list a single `/data` folder for the media, however, you can set up multiple mount points if you wish. For instance, you can set up 3 separate mountpoints named `/manga`, `/comics` and `/books`, each mapped to separate folders on host.

Image: `ghcr.io/linuxserver-playground/kavita:latest` ([https://github.com/linuxserver-playground/docker-kavita](https://github.com/linuxserver-playground/docker-kavita))
