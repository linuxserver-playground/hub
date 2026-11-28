# Plex

![Plex](https://raw.githubusercontent.com/linuxserver/docker-templates/master/linuxserver.io/img/plex-logo.png)

[Plex](https://plex.tv) organizes video, music and photos from personal media libraries and streams them to smart TVs, streaming boxes and mobile devices. This container is packaged as a standalone Plex Media Server. Straightforward design and bulk actions mean getting things done faster.

## Application setup

Webui can be found at `<your-ip>:32400/web`

?+note[Updates](|If there is no value set for the VERSION variable, then no updates will take place.|)

?+note[New users](|For new users, no updates will take place on the first run of the container as there is no preferences file to read your token from, to update restart the Docker container after logging in through the webui.|)

Valid settings for VERSION are:-

?+info[Plexpass](|YOU CANNOT UPDATE TO A PLEXPASS ONLY (BETA) VERSION IF YOU ARE NOT LOGGED IN WITH A PLEXPASS ACCOUNT.|)

+ **`docker`**: Let Docker handle the Plex Version, we keep our Dockerhub Endpoint up to date with the latest public builds. This is the same as leaving this setting out of your create command.
+ **`latest`**: will update plex to the latest version available that you are entitled to.
+ **`public`**: will update plexpass users to the latest public version, useful for plexpass users that don't want to be on the bleeding edge but still want the latest public updates.
+ **`<specific-version>`**: will select a specific version (eg 0.9.12.4.1192-9a47d21) of plex to install, note you cannot use this to access plexpass versions if you do not have plexpass.

Image: `ghcr.io/linuxserver-playground/plex:latest` ([https://github.com/linuxserver-playground/docker-plex](https://github.com/linuxserver-playground/docker-plex))
