# Syslog-ng

![Syslog-ng](https://raw.githubusercontent.com/linuxserver/docker-templates/master/linuxserver.io/img/syslog-ng-logo.png)

[syslog-ng](https://www.syslog-ng.com/products/open-source-log-management/) allows you to flexibly collect, parse, classify, rewrite and correlate logs from across your infrastructure and store or route them to log analysis tools.

## Application setup

Edit `/config/syslog-ng.conf` to configure your logging sources and destinations.

The application pid, control file, etc. are all kept in /config so when using tools such as `syslog-ng-ctl` you need to specify the path e.g. `syslog-ng-ctl reload -c /config/syslog-ng.ctl`

More info at [syslog-ng](https://www.syslog-ng.com/technical-documents/list/syslog-ng-open-source-edition).

Image: `ghcr.io/linuxserver-playground/syslog-ng:latest` ([https://github.com/linuxserver-playground/docker-syslog-ng](https://github.com/linuxserver-playground/docker-syslog-ng))
