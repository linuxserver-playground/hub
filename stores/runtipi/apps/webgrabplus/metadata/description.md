# Webgrabplus

![Webgrabplus](https://www.webgrabplus.com/sites/default/themes/WgTheme/images/slideshows/EPG_fading.jpg)

[Webgrabplus](https://www.webgrabplus.com) is a multi-site incremental xmltv epg grabber. It collects tv-program guide data from selected tvguide sites for your favourite channels.

## Application setup

To configure WebGrab+Plus follow the [documentation](https://www.webgrabplus.com/documentation/configuration/)

**Please note that depending on your host this container may not work with the `no-new-privileges=true` security-opt.**

Note that there are some things in the guide that does not apply to this container. Below you can find the changes.

**The configuration files are found where your config volume is mounted.**
**Do not change the filename tag in the configuration file!**

The /data volume mapping is where WebGrab+Plus outputs the xml file. To use the xml file in another program, you have to point it to the host path you mapped the /data volume to.

To adjust the scheduled cron job, you can apply our [universal cron mod](https://github.com/linuxserver/docker-mods/tree/universal-cron).

Image: `ghcr.io/linuxserver-playground/webgrabplus:latest` ([https://github.com/linuxserver-playground/docker-webgrabplus](https://github.com/linuxserver-playground/docker-webgrabplus))
