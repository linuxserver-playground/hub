# Vscodium-web

![Vscodium-web](https://raw.githubusercontent.com/linuxserver/docker-templates/master/linuxserver.io/img/vscodium-icon.png)

[Vscodium-web](https://vscodium.com/) is a community-driven, freely-licensed binary distribution of the remote host web component of Microsoft's editor VS Code.

## Application setup

>[!NOTE]
>This image sets up the `remote host web` component of VSCodium, which is only accessible in a web browser. If you are looking for the full desktop client of VSCodium, served over Selkies, see here: https://github.com/linuxserver/docker-vscodium

If `CONNECTION_TOKEN` or `CONNECTION_TOKEN_FILE` env vars are set, you can access the webui at `http://<your-ip>:8000/?tkn=supersecrettoken` (replace `supersecrettoken` with the value set). If not, you can access the webui at `http://<your-ip>:8000`.

For github integration, drop your ssh key in to `/config/.ssh`.
Then open a terminal from the top menu and set your github username and email via the following commands

```bash
git config --global user.name "username"
git config --global user.email "email address"
```

When reverse proxied through SWAG, custom services running on specific ports inside vscodium-web can be accessed at `https://PORT.vscodium-web.domain.com` very much like how code-server's port proxy function is handled. For that, a wildcard CNAME `*.vscodium-web.domain.com` needs to be created and the SWAG cert needs to cover those subdomains. Https access to a port can be initiated by adding an `s` to the end of the PORT in the url (ie. `https://PORTs.vscodium-web.domain.com`)

Image: `ghcr.io/linuxserver-playground/vscodium-web:latest` ([https://github.com/linuxserver-playground/docker-vscodium-web](https://github.com/linuxserver-playground/docker-vscodium-web))
