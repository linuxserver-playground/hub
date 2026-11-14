# Swag

![Swag](https://github.com/linuxserver/docker-templates/raw/master/linuxserver.io/img/swag.gif)

SWAG - Secure Web Application Gateway (formerly known as letsencrypt, no relation to Let's Encrypt™) sets up an Nginx webserver and reverse proxy with php support and a built-in certbot client that automates free SSL server certificate generation and renewal processes (Let's Encrypt and ZeroSSL). It also contains fail2ban for intrusion prevention.

## Application setup

### Validation and initial setup

* Before running this container, make sure that the url and subdomains are properly forwarded to this container's host, and that port 443 (and/or 80) is not being used by another service on the host (NAS gui, another webserver, etc.).
* If you need a dynamic dns provider, you can use the free provider duckdns.org where the `URL` will be `yoursubdomain.duckdns.org` and the `SUBDOMAINS` can be `www,ftp,cloud` with http validation, or `wildcard` with dns validation. You can use our [duckdns image](https://hub.docker.com/r/linuxserver/duckdns/) to update your IP on duckdns.org.
* For `http` validation, port 80 on the internet side of the router should be forwarded to this container's port 80
* For `dns` validation, make sure to enter your credentials into the corresponding ini (or json for some plugins) file under `/config/dns-conf`
  * Cloudflare provides free accounts for managing dns and is very easy to use with this image. Make sure that it is set up for "dns only" instead of "dns + proxy"
  * Google dns plugin is meant to be used with "Google Cloud DNS", a paid enterprise product, and not for "Google Domains DNS"
  * DuckDNS only supports two types of DNS validated certificates (not both at the same time):
    1. Certs that only cover your main subdomain (ie. `yoursubdomain.duckdns.org`, leave the `SUBDOMAINS` variable empty)
    2. Certs that cover sub-subdomains of your main subdomain (ie. `*.yoursubdomain.duckdns.org`, set the `SUBDOMAINS` variable to `wildcard`)
* `--cap-add=NET_ADMIN` is required for fail2ban to modify iptables
* After setup, navigate to `https://example.com` to access the default homepage (http access through port 80 is disabled by default, you can enable it by editing the default site config at `/config/nginx/site-confs/default.conf`).
* Certs are checked twice daily using ACME Renewal Information (ARI) to determine the optimal renewal window. If your cert is about to expire, check the logs under `/config/log/letsencrypt` to see why the renewals have been failing.

### Certbot Plugins

SWAG includes many Certbot plugins out of the box, but not all plugins can be included.
If you need a plugin that is not included, the quickest way to have the plugin available is to use our [Universal Package Install Docker Mod](https://github.com/linuxserver/docker-mods/tree/universal-package-install).

Set the following environment variables on your container:

```yaml
DOCKER_MODS=linuxserver/mods:universal-package-install
INSTALL_PIP_PACKAGES=certbot-dns-<plugin>
```

Set the required credentials (usually found in the plugin documentation) in `/config/dns-conf/<plugin>.ini`.
It is recommended to attempt obtaining a certificate with `STAGING=true` first to make sure the plugin is working as expected.

### Security and password protection

* The container detects changes to url and subdomains, revokes existing certs and generates new ones during start.
* Per [RFC7919](https://datatracker.ietf.org/doc/html/rfc7919), the container is shipping [ffdhe4096](https://ssl-config.mozilla.org/ffdhe4096.txt) as the `dhparams.pem`.
* If you'd like to password protect your sites, you can use htpasswd. Run the following command on your host to generate the htpasswd file `docker exec -it swag htpasswd -c /config/nginx/.htpasswd <username>`
* You can add multiple user:pass to `.htpasswd`. For the first user, use the above command, for others, use the above command without the `-c` flag, as it will force deletion of the existing `.htpasswd` and creation of a new one
* You can also use ldap auth for security and access control. A sample, user configurable ldap.conf is provided, and it requires the separate image [linuxserver/ldap-auth](https://hub.docker.com/r/linuxserver/ldap-auth/) to communicate with an ldap server.

### Site config and reverse proxy

* The default site config resides at `/config/nginx/site-confs/default.conf`. Feel free to modify this file, and you can add other conf files to this directory. However, if you delete the `default` file, a new default will be created on container start.
* Preset reverse proxy config files are added for popular apps. See the `README.md` file under `/config/nginx/proxy-confs` for instructions on how to enable them. The preset confs reside in and get imported from [this repo](https://github.com/linuxserver/reverse-proxy-confs).
* If you wish to hide your site from search engine crawlers, you may find it useful to add this configuration line to your site config, within the server block, above the line where ssl.conf is included
`add_header X-Robots-Tag "noindex, nofollow, nosnippet, noarchive";`
This will *ask* Google et al not to index and list your site. Be careful with this, as you will eventually be de-listed if you leave this line in on a site you wish to be present on search engines
* If you wish to redirect http to https, you must expose port 80

### Using certs in other containers

* This container includes auto-generated pfx and private-fullchain-bundle pem certs that are needed by other apps like Emby and Znc.
  * To use these certs in other containers, do either of the following:
  1. *(Easier)* Mount the container's config folder in other containers (ie. `-v /path-to-swag-config:/swag-ssl`) and in the other containers, use the cert location `/swag-ssl/keys/letsencrypt/`
  2. *(More secure)* Mount the SWAG folder `etc` that resides under `/config` in other containers (ie. `-v /path-to-swag-config/etc:/swag-ssl`) and in the other containers, use the cert location `/swag-ssl/letsencrypt/live/<your.domain.url>/` (This is more secure because the first method shares the entire SWAG config folder with other containers, including the www files, whereas the second method only shares the ssl certs)
  * These certs include:
  1. `cert.pem`, `chain.pem`, `fullchain.pem` and `privkey.pem`, which are generated by Certbot and used by nginx and various other apps
  2. `privkey.pfx`, a format supported by Microsoft and commonly used by dotnet apps such as Emby Server (no password)
  3. `priv-fullchain-bundle.pem`, a pem cert that bundles the private key and the fullchain, used by apps like ZNC

### Using fail2ban

* This container includes fail2ban set up with 5 jails by default:
  1. nginx-http-auth
  2. nginx-badbots
  3. nginx-botsearch
  4. nginx-deny
  5. nginx-unauthorized
* To enable or disable other jails, modify the file `/config/fail2ban/jail.local`
* To modify filters and actions, instead of editing the `.conf` files, create `.local` files with the same name and edit those because .conf files get overwritten when the actions and filters are updated. `.local` files will append whatever's in the `.conf` files (ie. `nginx-http-auth.conf` --> `nginx-http-auth.local`)
* You can check which jails are active via `docker exec -it swag fail2ban-client status`
* You can check the status of a specific jail via `docker exec -it swag fail2ban-client status <jail name>`
* You can unban an IP via `docker exec -it swag fail2ban-client set <jail name> unbanip <IP>`
* A list of commands for fail2ban-client can be found [here](https://manpages.ubuntu.com/manpages/noble/man1/fail2ban-client.1.html)

### Updating configs

* This container creates a number of configs for nginx, proxy samples, etc.
* Config updates are noted in the changelog but not automatically applied to your files.
* If you have modified a file with noted changes in the changelog:
  1. Keep your existing configs as is (not broken, don't fix)
  2. Review our repository commits and apply the new changes yourself
  3. Delete the modified config file with listed updates, restart the container, reapply your changes
* If you have NOT modified a file with noted changes in the changelog:
  1. Delete the config file with listed updates, restart the container
* Proxy sample updates are not listed in the changelog. See the changes here: [https://github.com/linuxserver/reverse-proxy-confs/commits/master](https://github.com/linuxserver/reverse-proxy-confs/commits/master)
* Proxy sample files WILL be updated, however your renamed (enabled) proxy files will not.
* You can check the new sample and adjust your active config as needed.

### QUIC support

This image supports QUIC (also known as HTTP/3) but it must be explicitly enabled in each proxy conf, and the default conf, because if the listener is enabled and you don't expose 443/UDP, it can break connections with some browsers.

To enable QUIC, expose 443/UDP to your clients, then uncomment both QUIC listeners in all of your active proxy confs, as well as the default conf, and restart the container.

You should also uncomment the `Alt-Svc` header in your `ssl.conf` so that browsers are aware that you offer QUIC connectivity.

It is [recommended](https://quic-go.net/docs/quic/optimizations/#udp-buffer-sizes) to increase the UDP send/recieve buffer **on the host** by setting the `net.core.rmem_max` and `net.core.wmem_max` sysctls. Suggested values are 4-16Mb (4194304-16777216 bytes). For persistence between reboots use `/etc/sysctl.d/`.

### Migration from the old `linuxserver/letsencrypt` image

Please follow the instructions [on this blog post](https://www.linuxserver.io/blog/2020-08-21-introducing-swag#migrate).

Image: `ghcr.io/linuxserver-playground/swag:latest` ([https://github.com/linuxserver-playground/docker-swag](https://github.com/linuxserver-playground/docker-swag))
