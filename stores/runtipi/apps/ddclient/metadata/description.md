# Ddclient

![Ddclient](https://raw.githubusercontent.com/linuxserver/docker-templates/master/linuxserver.io/img/ddclient-logo.png)

[Ddclient](https://github.com/ddclient/ddclient) is a Perl client used to update dynamic DNS entries for accounts on Dynamic DNS Network Service Provider. It was originally written by Paul Burry and is now mostly by wimpunk. It has the capability to update more than just dyndns and it can fetch your WAN-ipaddress in a few different ways.

## Application setup

Edit the `ddclient.conf` file found in your `/config` volume (also see official [ddclient documentation](https://ddclient.net)). This config file has many providers to choose from and you basically just have to uncomment your provider and add username/password where requested. If you modify ddclient.conf, ddclient will automaticcaly restart and read the config.

### Get dynamic IP from Fritz.Box
If ddclient shall fetch the dynamic (public) IP-address from a fritz.box (AVM) add the following line to `/config/ddclient.conf`:
````
use=cmd, cmd=/etc/ddclient/get-ip-from-fritzbox
````

Image: `ghcr.io/linuxserver-playground/ddclient:latest` ([https://github.com/linuxserver-playground/docker-ddclient](https://github.com/linuxserver-playground/docker-ddclient))
