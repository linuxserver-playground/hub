# Grocy

![Grocy](https://raw.githubusercontent.com/linuxserver/docker-templates/master/linuxserver.io/img/grocy-logo.png)

[Grocy](https://github.com/grocy/grocy) is an ERP system for your kitchen! Cut down on food waste, and manage your chores with this brilliant utility.

Keep track of your purchases, how much food you are wasting, what chores need doing and what batteries need charging with this proudly Open Source tool

For more information on grocy visit their website and check it out: https://grocy.info

## Application setup

Grocy is simple to get running. Configure the container with instructions below, start it, and you can then access it
by visiting http://your.ip:9283 - once the page loads, you can log in with the default username and password of admin / admin

### Upgrading

Following a container upgrade ensure that you visit the root (`/`) route (click on the logo in the left upper edge) in order to run any necessary database migrations. See [https://github.com/grocy/grocy#how-to-update](https://github.com/grocy/grocy#how-to-update) for more details.

Image: `ghcr.io/linuxserver-playground/grocy:latest` ([https://github.com/linuxserver-playground/docker-grocy](https://github.com/linuxserver-playground/docker-grocy))
