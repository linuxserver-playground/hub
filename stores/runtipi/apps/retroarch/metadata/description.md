# Retroarch

![Retroarch](https://raw.githubusercontent.com/linuxserver/docker-templates/master/linuxserver.io/img/retroarch-logo.png)

[RetroArch](https://retroarch.com/) is a frontend for emulators, game engines and media players. It enables you to run classic games on a wide range of computers and consoles through its slick graphical interface.

## Application setup

The application can be accessed at:

* https://yourhost:3001/

**Note: In pure CPU mode RetroArch will use LLVMPipe for menu rendering, when in game this is less of an issue. You can configure things like the menu refresh rate in your RetroArch settings or mount in an Nvidia GPU. When running with an Nvidia GPU it will be necesarry to right click the desktop and re-launch RetroArch on your first launch only.**

Image: `ghcr.io/linuxserver-playground/retroarch:latest` ([https://github.com/linuxserver-playground/docker-retroarch](https://github.com/linuxserver-playground/docker-retroarch))
