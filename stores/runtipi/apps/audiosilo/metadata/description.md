# Audiosilo

![Audiosilo](https://raw.githubusercontent.com/linuxserver/docker-templates/master/linuxserver.io/img/audiosilo-logo.png)

[AudioSilo](https://audiosilo.app) is a self-hosted audiobook server. Point it at your audiobook folders and listen from the built-in web player or the AudioSilo apps for iOS and Android, with listening progress synced across devices.

## Application setup

On first start AudioSilo creates an admin account and prints its password, plus an auth code for pairing devices, to the container log **once**, so check the log straight away (`docker logs audiosilo`).

The server listens on HTTPS with a self-signed certificate by default. Open `https://<your-ip>:8080/admin`, accept the certificate warning, sign in as `admin`, and add `/audiobooks` as a library. The web player is at `/web`. To connect a phone, enter the auth code on the page at `/`; it then shows the QR code the AudioSilo app scans.

Settings live in the admin console under **Server > Settings**, saved to `/config/config.yaml`. To run behind a reverse proxy such as SWAG, either proxy to the HTTPS port as is, or set **HTTPS mode** to **Off** (then restart the container) and let the proxy terminate TLS. Either way, set **Public address** to the proxied URL so invite links and pairing QR codes point there, and add the proxy's address to **Trusted proxies** so rate limiting sees your visitors' real addresses.

Any `AUDIOSILO_*` environment variable overrides its setting and shows as locked in the admin console. See the [configuration reference](https://docs.audiosilo.app/developers/server/configuration#environment-variables) for the full list.

Image: `ghcr.io/linuxserver-playground/audiosilo:latest` ([https://github.com/linuxserver-playground/docker-audiosilo](https://github.com/linuxserver-playground/docker-audiosilo))
