# Airsonic-advanced

![Airsonic-advanced](https://raw.githubusercontent.com/linuxserver/docker-templates/master/linuxserver.io/img/airsonic-banner.png)

[Airsonic-advanced](https://github.com/kagemomiji/airsonic-advanced) is a free, web-based media streamer, providing ubiquitious access to your music. Use it to share your music with friends, or to listen to your own music while at work. You can stream to multiple players simultaneously, for instance to one player in your kitchen and another in your living room.

## Application setup

We don't formally support upgrading from Airsonic to Airsonic Advanced, it may or may not work for you and we'd recommend making backups before attempting this. Following the upgrade you may experience a forced rescan of your library so take this into account if you have a lot of files.

Please see notes about upgrading from v10 to v11 [here](https://github.com/kagemomiji/airsonic-advanced#usage)

Access WebUI at `<your-ip>:4040`.

Default user/pass is admin/admin

Extra java options can be passed with the JAVA_OPTS environment variable, eg `-e JAVA_OPTS="-Xmx256m -Xms256m"`. For some reverse proxies, you may need to pass `JAVA_OPTS=-Dserver.use-forward-headers=true` for airsonic to generate the proper URL schemes.

Note that if you want to use [Airsonic's Java jukebox player](https://airsonic.github.io/docs/jukebox/), then `PGID` will need to match the group of your sound device (e.g. `/dev/snd`).

Image: `ghcr.io/linuxserver-playground/airsonic-advanced:latest` ([https://github.com/linuxserver-playground/docker-airsonic-advanced](https://github.com/linuxserver-playground/docker-airsonic-advanced))
