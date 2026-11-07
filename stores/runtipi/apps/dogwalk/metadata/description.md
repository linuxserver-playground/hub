# Dogwalk

![Dogwalk](https://raw.githubusercontent.com/linuxserver/docker-templates/master/linuxserver.io/img/dogwalk-logo.png)

[DOGWALK](https://studio.blender.org/projects/dogwalk/) is Blender Studio's long awaited second game project, focused on creating a bite-sized interactive storytelling playground. Play as a big adorable dog and explore the winter woods with a little kid.

## Application setup

The application can be accessed at:

* https://yourhost:3001/

**This game is currently buggy on Linux and this is known, it segfaults when trying to continue or launch a new game for the second time. As a workaround we purge their storage directory on every launch, so saving and continue is not available, hopefully this will be fixed in future versions. Not mashing buttons when the splash screen is loading helps a lot in testing.**

**This container REQUIRES a GPU, either Nvidia via runtime or Intel/AMD via `--device /dev/dri:/dev/dri` it will not work without one, you will only see a gray screen on launch without one.**

**Controller input is the best option, but if you lack a controller use gaming mode which will pointer lock your mouse at fullscreen.**

Image: `ghcr.io/linuxserver-playground/dogwalk:latest` ([https://github.com/linuxserver-playground/docker-dogwalk](https://github.com/linuxserver-playground/docker-dogwalk))
