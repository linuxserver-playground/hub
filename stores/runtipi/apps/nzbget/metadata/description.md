# Nzbget

![Nzbget](https://raw.githubusercontent.com/linuxserver/docker-templates/master/linuxserver.io/img/nzbget-banner.png)

[Nzbget](http://nzbget.com/) is a usenet downloader, written in C++ and designed with performance in mind to achieve maximum download speed by using very little system resources.

## Application setup

Webui can be found at `<your-ip>:6789` and the default login details (change ASAP) are

`login:nzbget, password:tegbzn6789`

To allow scheduling, from the webui set the time correction value in settings/logging.

You can add an additional mount point for intermediate unpacking folder with:-

`-v /path/to/nzbget/intermediate:/intermediate`

for example, and changing the setting for InterDir in the PATHS tab of settings to `/intermediate`

Image: `ghcr.io/linuxserver-playground/nzbget:latest` ([https://github.com/linuxserver-playground/docker-nzbget](https://github.com/linuxserver-playground/docker-nzbget))
