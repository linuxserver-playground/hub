# Mastodon

![Mastodon](https://raw.githubusercontent.com/linuxserver/docker-templates/master/linuxserver.io/img/mastodon-banner.png)

[Mastodon](https://github.com/mastodon/mastodon/) is a free, open-source social network server based on ActivityPub where users can follow friends and discover new ones..

## Application setup

We provide aliases for the common commands that execute in the correct context so that environment variables from secrets are available to them:

* To generate keys for `SECRET_KEY_BASE` & `OTP_SECRET` run `docker run --rm -it --entrypoint /bin/bash lscr.io/linuxserver/mastodon:latest generate-secret` once for each.

* To generate keys for `VAPID_PRIVATE_KEY` & `VAPID_PUBLIC_KEY` run `docker run --rm -it --entrypoint /bin/bash lscr.io/linuxserver/mastodon:latest generate-vapid`

* To generate keys for `ACTIVE_RECORD_ENCRYPTION_DETERMINISTIC_KEY`, `ACTIVE_RECORD_ENCRYPTION_KEY_DERIVATION_SALT`, & `ACTIVE_RECORD_ENCRYPTION_PRIMARY_KEY` run `docker run --rm -it --entrypoint /bin/bash lscr.io/linuxserver/mastodon:latest generate-active-record`

Both of the secret generation aliases above can be run without any other setup having been carried out.

* To use `tootctl` you can run something like `docker exec -it lscr.io/linuxserver/mastodon /tootctl <command>`

Using `tootctl` requires you to complete the initial Mastodon configuration first.

This container *requires* separate postgres and redis instances to run.

We support all of the official [environment variables](https://docs.joinmastodon.org/admin/config) for configuration. In place of adding them all to your run/compose you can use an env file such as [this example](https://github.com/mastodon/mastodon/blob/main/.env.production.sample) from the upstream project.

For more information check out the [mastodon documentation](https://docs.joinmastodon.org/).

### Running separate sidekiq instances

It is currently only supported to run a single queue per container instance *or* all queues in a single container instance.

All containers must share the same `/config` mount and be on a common docker network.

### NO_CHOWN Option

On larger Mastodon instances, our init process to verify that permissions are set correctly can noticeably slow down the container startup. If you are experiencing this, you can set `NO_CHOWN` to `true` to skip that step of the init.

*Do NOT set this on first run of the container. If you enable this option you are taking full responsibility for ensuring that the permissions in your /config mount are correct. If you're even slightly unsure, don't set it.*

### Strict reverse proxies

This image automatically redirects to https with a self-signed certificate. If you are using a reverse proxy which validates certificates, you need to [disable this check for the container](https://docs.linuxserver.io/faq#strict-proxy).

Image: `ghcr.io/linuxserver-playground/mastodon:latest` ([https://github.com/linuxserver-playground/docker-mastodon](https://github.com/linuxserver-playground/docker-mastodon))
