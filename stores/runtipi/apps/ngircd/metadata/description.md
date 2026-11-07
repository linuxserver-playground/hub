# Ngircd

![Ngircd](https://raw.githubusercontent.com/linuxserver/docker-templates/master/linuxserver.io/img/ngircd-logo.png)

[Ngircd](https://ngircd.barton.de/) is a free, portable and lightweight Internet Relay Chat server for small or private networks, developed under the GNU General Public License (GPL). It is easy to configure, can cope with dynamic IP addresses, and supports IPv6, SSL-protected connections as well as PAM for authentication. It is written from scratch and not based on the original IRCd.

## Application setup

* To setup ngircd you will need to edit `/config/ngircd.conf` which is created the first time the container is run, edit the file and restart the container to implement any config changes.
* For information see the ngircd site [here.](https://github.com/ngircd/ngircd/blob/master/doc/sample-ngircd.conf.tmpl)

Image: `ghcr.io/linuxserver-playground/ngircd:latest` ([https://github.com/linuxserver-playground/docker-ngircd](https://github.com/linuxserver-playground/docker-ngircd))
