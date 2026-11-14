# Jellyfin

![Jellyfin](https://raw.githubusercontent.com/linuxserver/docker-templates/master/linuxserver.io/img/jellyfin-logo.png)

[Jellyfin](https://github.com/jellyfin/jellyfin) is a Free Software Media System that puts you in control of managing and streaming your media. It is an alternative to the proprietary Emby and Plex, to provide media from a dedicated server to end-user devices via multiple apps. Jellyfin is descended from Emby's 3.5.2 release and ported to the .NET Core framework to enable full cross-platform support. There are no strings attached, no premium licenses or features, and no hidden agendas: just a team who want to build something better and work together to achieve it.

## Application setup

Webui can be found at `http://<your-ip>:8096`

More information can be found on the official documentation [here](https://jellyfin.org/docs/general/quick-start.html).

### Hardware Acceleration Enhancements

This section lists the enhancements we have made for hardware acceleration in this image specifically.

### Intel

To enable the OpenCL based DV, HDR10 and HLG tone-mapping, please refer to the OpenCL-Intel mod from here:

https://mods.linuxserver.io/?mod=jellyfin

And follow this guide even if you are using iGPU: https://jellyfin.org/docs/general/administration/hardware-acceleration/intel/#configure-and-verify-lp-mode-on-linux

Image: `ghcr.io/linuxserver-playground/jellyfin:latest` ([https://github.com/linuxserver-playground/docker-jellyfin](https://github.com/linuxserver-playground/docker-jellyfin))
