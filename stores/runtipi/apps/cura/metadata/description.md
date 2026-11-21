# Cura

![Cura](https://raw.githubusercontent.com/linuxserver/docker-templates/master/linuxserver.io/img/cura-logo.png)

[UltiMaker Cura](https://ultimaker.com/software/ultimaker-cura/) is free, easy-to-use 3D printing software trusted by millions of users. Fine-tune your 3D model with 400+ settings for the best slicing and printing results.

## Application setup

The application can be accessed at:

* https://yourhost:3001/

**Cura has a known bug that it will OOM and crash unless you set `preferences > confgure cura > Disable: crash reports, updates, notifications`, this is a hard requirement or it will OOM.**

Image: `ghcr.io/linuxserver-playground/cura:latest` ([https://github.com/linuxserver-playground/docker-cura](https://github.com/linuxserver-playground/docker-cura))
