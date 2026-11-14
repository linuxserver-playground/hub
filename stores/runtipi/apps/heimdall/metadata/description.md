# Heimdall

![Heimdall](https://raw.githubusercontent.com/linuxserver/docker-templates/master/linuxserver.io/img/heimdall-banner.png)

[Heimdall](https://heimdall.site) is a way to organise all those links to your most used web sites and web applications in a simple way.

Simplicity is the key to Heimdall.

Why not use it as your browser start page? It even has the ability to include a search bar using either Google, Bing or DuckDuckGo.

## Application setup

Access the web gui at http://SERVERIP:PORT

### Adding password protection

This image now supports password protection through htpasswd. Run the following command on your host to generate the htpasswd file `docker exec -it heimdall htpasswd -c /config/nginx/.htpasswd <username>`. Replace <username> with a username of your choice and you will be asked to enter a password. Uncomment the `basic auth` lines in `/config/nginx/site-confs/default.conf` and restart the container.

Image: `ghcr.io/linuxserver-playground/heimdall:latest` ([https://github.com/linuxserver-playground/docker-heimdall](https://github.com/linuxserver-playground/docker-heimdall))
