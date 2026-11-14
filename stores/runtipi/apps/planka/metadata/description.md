# Planka

![Planka](https://raw.githubusercontent.com/linuxserver/docker-templates/master/linuxserver.io/img/planka-logo.png)

[Planka](https://github.com/plankanban/planka/) is an elegant open source project tracking tool.

## Application setup

Web UI is accessible at http://SERVERIP:PORT. An external postgres database is required.

Once you've run your first time setup you can safely remove the DEFAULT_ environment variables. They will overwrite any changes made to the default user in the web UI (passwords, display names, etc.) on startup if left in place.

### Migration from Official Image

Copy your `user-avatars`, `background-images`, and `attachments` folders to your new `/config` mount so that it looks like:

```text
/config
├── attachments
└── images
    ├── background-images
    └── user-avatars
```

Image: `ghcr.io/linuxserver-playground/planka:latest` ([https://github.com/linuxserver-playground/docker-planka](https://github.com/linuxserver-playground/docker-planka))
