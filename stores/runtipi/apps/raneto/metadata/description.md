# Raneto

![Raneto](https://raw.githubusercontent.com/linuxserver/docker-templates/master/linuxserver.io/img/raneto-logo.png)

[Raneto](http://raneto.com/) - is an open source Knowledgebase platform that uses static Markdown files to power your Knowledgebase.

## Application setup

Access the webui at http://<your-ip>:3000

The default username and password is *admin/password*

This application can only be configured through file storage the web interface is only for editing Markdown files.
You need to understand the following paths and the role they play for the application:

* /config/config/config.js - Main configuration file to setup your user, site name, etc.
* /config/content - All of your Markdown files go here [more info](http://docs.raneto.com/usage/creating-pages).
* /config/images - This folder will serve content on http://<your-ip>:3000/images/<image name>.png you can put anything in here but it is specifically for image files so you can embed them in your Markdown files without using external hosting.

Image: `ghcr.io/linuxserver-playground/raneto:latest` ([https://github.com/linuxserver-playground/docker-raneto](https://github.com/linuxserver-playground/docker-raneto))
