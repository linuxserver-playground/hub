# Calibre

![Calibre](https://raw.githubusercontent.com/linuxserver/docker-templates/master/linuxserver.io/img/calibre-logo.png)

[Calibre](https://calibre-ebook.com/) is a powerful and easy to use e-book manager. Users say it's outstanding and a must-have. It'll allow you to do nearly everything and it takes things a step beyond normal e-book software. It's also completely free and open source and great for both casual users and computer experts.

## Application setup

The application can be accessed at:

* https://yourhost:8181/

In the wizard, make sure to select the default library location `/config/Calibre Library` as the path for books. We will not provide support if you use a different path.

Calibre's built-in webserver is not enabled by default. If you wish to use it, please enable it in Calibre Preferences under `Sharing over the net`. Make sure to leave the port setting as `8081` and check the box to start it automatically.

Image: `ghcr.io/linuxserver-playground/calibre:latest` ([https://github.com/linuxserver-playground/docker-calibre](https://github.com/linuxserver-playground/docker-calibre))
