# Calibre-web

![Calibre-web](https://raw.githubusercontent.com/linuxserver/docker-templates/master/linuxserver.io/img/calibre-web-icon.png)

[Calibre-web](https://github.com/janeczku/calibre-web) is a web app providing a clean interface for browsing, reading and downloading eBooks using an existing Calibre database.   It is also possible to integrate google drive and edit metadata and your calibre library through the app itself.

This software is a fork of library and licensed under the GPL v3 License.

## Application setup

Webui can be found at `http://your-ip:8083`

On the initial setup screen, enter `/books` as your calibre library location.

**Default admin login:**
*Username:* admin
*Password:* admin123

If you lock yourself out or forget a password, you will need to specify the app.db similar to this:
`docker exec -it calibre-web python3 /app/calibre-web/cps.py -p /config/app.db -s <user>:<pass>`
If you fail to specify the proper db, it will appear to succeed, but it will not work.

Unrar is included by default and needs to be set in the Calibre-Web admin page (Basic Configuration:External Binaries) with a path of `/usr/bin/unrar`

**64bit only** We have implemented the optional ability to pull in the dependencies to enable ebook conversion utilising Calibre, this means if you don't require this feature the container isn't uneccessarily bloated but should you require it, it is easily available.
This optional layer will be rebuilt automatically on our CI pipeline upon new Calibre releases so you can stay up to date.
To use this option add the optional environmental variable as shown in the docker-mods section to pull an addition docker layer to enable ebook conversion and then in the Calibre-Web admin page (Basic Configuration:External Binaries) set the **Path to Calibre E-Book Converter** to `/usr/bin/ebook-convert` on versions 0.6.21 and lower. For 0.6.22 and higher, set the directory, `/usr/bin/` only.

This image contains the [kepubify](https://pgaskin.net/kepubify/) ebook conversion tool (MIT License) to convert epub to kepub.  In the Calibre-Web admin page (Basic Configuration:External Binaries) set the **Path to Kepubify E-Book Converter** to `/usr/bin/kepubify`

Image: `ghcr.io/linuxserver-playground/calibre-web:latest` ([https://github.com/linuxserver-playground/docker-calibre-web](https://github.com/linuxserver-playground/docker-calibre-web))
