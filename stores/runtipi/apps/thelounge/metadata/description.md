# Thelounge

![Thelounge](https://raw.githubusercontent.com/thelounge/thelounge/master/client/img/logo-vertical-transparent-bg.svg?sanitize=true)

[Thelounge](https://thelounge.github.io/) (a fork of shoutIRC) is a web IRC client that you host on your own server.

## Application setup

* When the application first runs, it will populate its /config

* Stop the container

* Now from the host, edit `/config/config.js`, wherever you've mapped it

* In most cases you want the value `public: false` to allow named users only

* Setting the two prefetch values to true improves usability, but uses more storage

* Once you have the configuration you want, save it and start the container again

* For each user, run the command

* `docker exec -it thelounge s6-setuidgid abc thelounge add <user>`

* You will be prompted to enter a password that will not be echoed.

* Saving logs to disk is the default, this consumes more space but allows scrollback.

* To log in to the application, browse to `http://<hostip>:9000`

* You should now be prompted for a username and password on the web interface.

* Once logged in, you can add an IRC network. Some defaults are preset for Freenode

Image: `ghcr.io/linuxserver-playground/thelounge:latest` ([https://github.com/linuxserver-playground/docker-thelounge](https://github.com/linuxserver-playground/docker-thelounge))
