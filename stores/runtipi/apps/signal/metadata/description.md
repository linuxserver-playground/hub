# Signal

![Signal](https://raw.githubusercontent.com/linuxserver/docker-templates/master/linuxserver.io/img/signal-logo.png)

[Signal](https://signal.org/) is a messaging app with privacy at its core. It is free and easy to use, with strong end-to-end encryption that keeps your communication completely private.

## Application setup

The application can be accessed at:

* https://yourhost:3001/

>[!WARNING]
>This container does not encrypt Signal's config.json using a secret manager like gnome-keyring or kwallet, the file is stored in plaintext.

Image: `ghcr.io/linuxserver-playground/signal:latest` ([https://github.com/linuxserver-playground/docker-signal](https://github.com/linuxserver-playground/docker-signal))
