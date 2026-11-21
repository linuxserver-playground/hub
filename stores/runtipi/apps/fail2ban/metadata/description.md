# Fail2ban

![Fail2ban](https://raw.githubusercontent.com/linuxserver/docker-templates/master/linuxserver.io/img/fail2ban-logo.png)

[Fail2ban](http://www.fail2ban.org/) is a daemon to ban hosts that cause multiple authentication errors.

## Application setup

This container is designed to allow fail2ban to function at the host level, as well as at the docker container level.
If you are running applications on the host, you will need to set the `chain` to `INPUT` in the jail for that application.

### [Configuration Files](https://github.com/linuxserver/fail2ban-confs)

On first run, the container will create a number of folders and files in `/config`. The default configurations for fail2ban are all disabled by default.

Please refer to the [Configuration README](https://github.com/linuxserver/fail2ban-confs/blob/master/README.md), which can be viewed in our repository, or in your config folder at `/config/fail2ban/README.md`.

### Remote Logs

All jails require the ability to read the application log files.
We recommend mounting each application's log folder as a volume to the container (illustrated by the optional volumes in our documentation).
Mounting individual log files can cause issues and is not recommended.

The `/remotelogs` path is designed to act as a parent for all log files you would like fail2ban to be able to use.
Each log file should be mounted in a subfolder underneath `/remotelogs`, ex:
- `/remotelogs/nginx/` would mount a folder containing the nginx logs to the container

Image: `ghcr.io/linuxserver-playground/fail2ban:latest` ([https://github.com/linuxserver-playground/docker-fail2ban](https://github.com/linuxserver-playground/docker-fail2ban))
