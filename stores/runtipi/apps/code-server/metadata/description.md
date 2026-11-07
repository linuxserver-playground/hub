# Code-server

![Code-server](https://raw.githubusercontent.com/linuxserver/docker-templates/master/linuxserver.io/img/code-server-banner.png)

[Code-server](https://coder.com) is VS Code running on a remote server, accessible through the browser.
- Code on your Chromebook, tablet, and laptop with a consistent dev environment.
- If you have a Windows or Mac workstation, more easily develop for Linux.
- Take advantage of large cloud servers to speed up tests, compilations, downloads, and more.
- Preserve battery life when you're on the go.
- All intensive computation runs on your server.
- You're no longer running excess instances of Chrome.

## Application setup

Access the webui at `http://<your-ip>:8443`.
For github integration, drop your ssh key in to `/config/.ssh`.
Then open a terminal from the top menu and set your github username and email via the following commands

```bash
git config --global user.name "username"
git config --global user.email "email address"
```

### Hashed code-server password

How to create the [hashed password](https://github.com/cdr/code-server/blob/master/docs/FAQ.md#can-i-store-my-password-hashed).

Image: `ghcr.io/linuxserver-playground/code-server:latest` ([https://github.com/linuxserver-playground/docker-code-server](https://github.com/linuxserver-playground/docker-code-server))
