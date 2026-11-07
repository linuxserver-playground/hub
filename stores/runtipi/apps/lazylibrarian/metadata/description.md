# Lazylibrarian

![Lazylibrarian](https://raw.githubusercontent.com/linuxserver/docker-templates/master/linuxserver.io/img/lazylibrarian-icon.png)

[Lazylibrarian](https://lazylibrarian.gitlab.io/) is a program to follow authors and grab metadata for all your digital reading needs. It uses a combination of Goodreads Librarything and optionally GoogleBooks as sources for author info and book info.  This container is based on the DobyTang fork.

## Application setup

Access the webui at `http://<your-ip>:5299/home`, for more information check out [Lazylibrarian](https://lazylibrarian.gitlab.io/).

We have set `/books` as optional path, this is because it is the easiest way to get started.

### Calibredb import

**64bit only** We have implemented the optional ability to pull in the dependencies to enable the Calibredb import program:, this means if you don't require this feature the container isn't unnecessarily bloated but should you require it, it is easily available.
This optional layer will be rebuilt automatically on our CI pipeline upon new Calibre releases so you can stay up to date.
To use this option add the optional environmental variable as detailed in the docker-mods section to pull an addition docker layer to enable ebook conversion and then in the LazyLibrarian config page (Processing:Calibredb import program:) set the path to converter tool to `/usr/bin/calibredb`

### ffmpeg

By adding `linuxserver/mods:lazylibrarian-ffmpeg` to your `DOCKER_MODS` environment variable you can install ffmpeg into your container on startup.
This allows you to use the audiobook conversion features of LazyLibrarian.
You can enable it in the Web UI under Settings > Processing > External Programs by setting the ffmpeg path to `ffmpeg`.

Image: `ghcr.io/linuxserver-playground/lazylibrarian:latest` ([https://github.com/linuxserver-playground/docker-lazylibrarian](https://github.com/linuxserver-playground/docker-lazylibrarian))
