# Sealskin

![Sealskin](https://raw.githubusercontent.com/linuxserver/docker-templates/master/linuxserver.io/img/sealskin-logo.png)

[Sealskin](https://github.com/selkies-project/sealskin/) is a self-hosted browser isolation and remote application streaming platform. It runs desktop applications in isolated containers on a server you control and streams them to any browser or phone. Clients include a browser extension, mobile apps, and a web app served by the server itself. Each turns links, files, downloads, and text selections into something you open remotely instead of locally, so nothing from the web runs on the device in front of you.

## Application setup

This image hosts the server component of the SealSkin platform: the API, the Caddy proxy, and the web app it serves. The full documentation lives at [selkies-project.github.io/sealskin](https://selkies-project.github.io/sealskin/).

## Clients

| Client | Where | Notes |
| --- | --- | --- |
| Chrome, Edge, Brave and other Chromium browsers | [Chrome Web Store](https://chromewebstore.google.com/detail/sealskin-isolation/lclgfmnljgacfdpmmmjmfpdelndbbfhk) | Full feature set, works with the self-signed certificate. |
| Firefox | [Firefox Add-ons](https://addons.mozilla.org/en-US/firefox/addon/sealskin-isolation/) | Requires a trusted certificate. |
| iOS | [App Store](https://apps.apple.com/us/app/sealskin/id6758210210) | Requires a trusted certificate. |
| Android | [Google Play](https://play.google.com/store/apps/details?id=io.linuxserver.sealskin) | Requires a trusted certificate. |
| Any browser | `https://<server>:8443/` | The web app: launcher, sessions, files and dashboard with nothing installed. Requires a trusted certificate. |

>[!NOTE]
>If you are not using a trusted SSL certificate (the default is self signed in `/config/ssl`) then only the Chrome extension can be used, and whatever port is mapped to 8000 must also be reachable so it can fall back to E2EE over HTTP. Firefox, the mobile apps and the web app enforce HTTPS.

## First run

On the first start with an empty `/config` the container generates a self-signed certificate for the proxy and the server's RSA key, then the server finds no administrator and writes two credentials for the built-in `admin` account:

* `/config/root_key` is an application key for the **web app**. Open `https://<server>:8443/` and paste it in to sign in.
* `/config/admin.json` is the key file for the **browser extension and mobile apps**. If `HOST_URL` was set it can be imported as is, otherwise edit it and replace the string `HOST_URL` with your server's IP or hostname.

>[!NOTE]
>Copy both files somewhere safe and delete them from the server. They are the only copy of that private key, the server keeps just the public half.

Once signed in you can install applications from the App Store, create users and groups, and make application keys for other devices from the dashboard.

On the web the root key is the only sign-in the server handles itself. Everyone else signs in through an identity provider (OpenID Connect or SAML) or a reverse proxy that signs users in, whose groups make administrators and carry limits. See [Signing in](https://selkies-project.github.io/sealskin/signin) before inviting a second person. Extension and mobile users can also be given key files from the Users panel.

## Scripted installation

Included in this repository is a helper script to spin up SealSkin with a trusted certificate using Duck DNS. Before using this script please navigate to [https://www.duckdns.org/](https://www.duckdns.org/), log in, make a sub domain, and get your token.

```bash
mkdir sealskin
cd sealskin
bash <(curl -sSL https://raw.githubusercontent.com/linuxserver/docker-sealskin/refs/heads/master/install.sh)
```

This will set up pathing, ownership, the compose file, and a trusted wildcard SSL certificate for Duck DNS.

You can also renew your wildcard SSL certificate by running the same script again in the same directory.

```bash
cd sealskin
bash <(curl -sSL https://raw.githubusercontent.com/linuxserver/docker-sealskin/refs/heads/master/install.sh)
```

## Basic Requirements

* **The container must be named `sealskin`.** The server inspects its own container to learn the host paths behind `/config` and `/storage`, the externally mapped ports, and the Docker network. The name is also the server's identity in its own records, so a container recreated under another name is another node. If you cannot keep the name, set `hostname: sealskin` or `SEALSKIN_NODE_NAME`.
* **The Docker socket is required.** Every session is a container the server starts through it. If launches fail with a permission error, make the socket group writable on the host with `sudo chmod g+rw /var/run/docker.sock`.
* **`PUID` and `PGID` own everything.** The server, its files and every session container run as that user, so `/config` and `/storage` on the host must be writable by it.
* **Ports.** 8443 carries the web app, the API and the streamed sessions. 8000 is only needed for the Chrome self-signed fallback. 8444 is the peer listener, only publish it to join several servers into a [cluster](https://selkies-project.github.io/sealskin/cluster).

The server can be exposed directly to the internet, its own Caddy instance terminates TLS and authenticates every request to a session. It can also run [behind a reverse proxy](https://selkies-project.github.io/sealskin/reverse-proxy) by setting `SEALSKIN_PUBLIC_URL` and `SEALSKIN_TRUSTED_PROXIES`, plus `SEALSKIN_HTTP_PORT` for a proxy that terminates TLS, with guides for SWAG, Traefik, Nginx Proxy Manager and Caddy. Every environment variable the server reads is listed in the [Settings Reference](https://selkies-project.github.io/sealskin/settings). The same image also runs on [Kubernetes](https://selkies-project.github.io/sealskin/kubernetes) from the upstream manifest, with sessions as pods.

### NVIDIA Support

NVIDIA support requires the proprietary driver 580 or newer (no MIT/GPL kernel modules) with the `nvidia-drm.modeset=1` kernel parameter set, and the NVIDIA Container Toolkit v1.20.1 or higher registered with Docker. The toolkit's refresh service creates the modeset device at boot so headless hosts need nothing more.

## Key & Certificate Management

The server requires several cryptographic keys to function. You can either let the container perform an automatic setup on its first run or provide your own for more control.

### Automatic First-Run Setup (Recommended)

On the first launch with an empty `/config` volume:

1. An init process generates the mandatory server key (`ssl/server_key.pem`) and a self-signed SSL certificate for the proxy (`ssl/proxy_key.pem`, `ssl/proxy_cert.pem`).
2. The server detects that no administrator exists, creates the default user `admin`, and writes `/config/admin.json` and `/config/root_key` as described above.

### Manual Pre-Configuration (Advanced)

Place the files in the `/config` volume **before** the first launch.

*   **To use a custom Admin Key:**
    1.  Generate your own RSA keypair.
    2.  Create a file containing only your **public key** PEM data at `/path/to/config/.config/sealskin/keys/admins/admin`.
    3.  The server will detect this file and write no `admin.json`. You use your private key to log in from the extension, and `admin` signs in to the web app with the root key alone.

*   **To use a custom SSL Certificate:**
    *   Place your certificate and private key at `/path/to/config/ssl/proxy_cert.pem` and `/path/to/config/ssl/proxy_key.pem`. This overrides the self-signed certificate and can be replaced later with a restart.

*   **To use a custom Server E2EE Key:**
    *   Place your RSA private key at `/path/to/config/ssl/server_key.pem`. This is the core key for the API's end-to-end encryption and validates the server when a client is configured with its public key.
        *   **Generation Command:** `openssl genpkey -algorithm RSA -out /path/to/config/ssl/server_key.pem -pkeyopt rsa_keygen_bits:4096`
        *   **Extraction Command (public key for clients):** `openssl rsa -in server_key.pem -pubout`

## Upgrading from 0.3

Nothing on disk needs changing, existing users, groups, installed apps, templates and sessions load as before and key files keep working. On the first start after the upgrade the server writes `/config/root_key` for the web app, sign in with it then copy and delete the file. Keep the container name `sealskin` or set `SEALSKIN_NODE_NAME` so the server keeps its identity. Collaboration rooms need application images with a Selkies release after 2.0.0, and NVIDIA hosts need the Container Toolkit v1.20.1 or higher.

Image: `ghcr.io/linuxserver-playground/sealskin:latest` ([https://github.com/linuxserver-playground/docker-sealskin](https://github.com/linuxserver-playground/docker-sealskin))
