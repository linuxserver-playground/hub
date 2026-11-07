# Wireguard

![Wireguard](https://www.wireguard.com/img/wireguard.svg)

[WireGuard®](https://www.wireguard.com/) is an extremely simple yet fast and modern VPN that utilizes state-of-the-art cryptography. It aims to be faster, simpler, leaner, and more useful than IPsec, while avoiding the massive headache. It intends to be considerably more performant than OpenVPN. WireGuard is designed as a general purpose VPN for running on embedded interfaces and super computers alike, fit for many different circumstances. Initially released for the Linux kernel, it is now cross-platform (Windows, macOS, BSD, iOS, Android) and widely deployable. It is currently under heavy development, but already it might be regarded as the most secure, easiest to use, and simplest VPN solution in the industry.

## Application setup

During container start, it will first check if the wireguard module is already installed and loaded. All currently supported kernels should have the wireguard module built-in (along with some older custom kernels). However, the module may not be enabled. Make sure it is enabled prior to starting the container.

This can be run as a server or a client, based on the parameters used.

## Note on iptables

Some hosts may not load the iptables kernel modules by default. In order for the container to be able to load them, you need to assign the `SYS_MODULE` capability and add the optional `/lib/modules` volume mount. Alternatively you can `modprobe` them from the host before starting the container.

## Server Mode

If the environment variable `PEERS` is set to a number or a list of strings separated by comma, the container will run in server mode and the necessary server and peer/client confs will be generated. The peer/client config qr codes will be output in the docker log if `LOG_CONFS` is set to `true`. They will also be saved in text and png format under `/config/peerX` in case `PEERS` is a variable and an integer or `/config/peer_X` in case a list of names was provided instead of an integer.

Variables `SERVERURL`, `SERVERPORT`, `INTERNAL_SUBNET`, `PEERDNS`, `INTERFACE`, `ALLOWEDIPS` and `PERSISTENTKEEPALIVE_PEERS` are optional variables used for server mode. Any changes to these environment variables will trigger regeneration of server and peer confs. Peer/client confs will be recreated with existing private/public keys. Delete the peer folders for the keys to be recreated along with the confs.

To add more peers/clients later on, you increment the `PEERS` environment variable or add more elements to the list and recreate the container.

To display the QR codes of active peers again, you can use the following command and list the peer numbers as arguments: `docker exec -it wireguard /app/show-peer 1 4 5` or `docker exec -it wireguard /app/show-peer myPC myPhone myTablet` (Keep in mind that the QR codes are also stored as PNGs in the config folder).

The templates used for server and peer confs are saved under `/config/templates`. Advanced users can modify these templates and force conf generation by deleting `/config/wg_confs/wg0.conf` and restarting the container.

The container managed server conf is hardcoded to `wg0.conf`. However, the users can add additional tunnel config files with `.conf` extensions into `/config/wg_confs/` and the container will attempt to start them all in alphabetical order. If any one of the tunnels fail, they will all be stopped and the default route will be deleted, requiring user intervention to fix the invalid conf and a container restart.

## Client Mode

Do not set the `PEERS` environment variable. Drop your client conf(s) into the config folder as `/config/wg_confs/<tunnel name>.conf` and start the container. If there are multiple tunnel configs, the container will attempt to start them all in alphabetical order. If any one of the tunnels fail, they will all be stopped and the default route will be deleted, requiring user intervention to fix the invalid conf and a container restart.

If you get IPv6 related errors in the log and connection cannot be established, edit the `AllowedIPs` line in your peer/client wg0.conf to include only `0.0.0.0/0` and not `::/0`; and restart the container.

## Road warriors, roaming and returning home

If you plan to use Wireguard both remotely and locally, say on your mobile phone, you will need to consider routing. Most firewalls will not route ports forwarded on your WAN interface correctly to the LAN out of the box. This means that when you return home, even though you can see the Wireguard server, the return packets will probably get lost.

This is not a Wireguard specific issue and the two generally accepted solutions are NAT reflection (setting your edge router/firewall up in such a way as it translates internal packets correctly) or split horizon DNS (setting your internal DNS to return the private rather than public IP when connecting locally).

Both of these approaches have positives and negatives however their setup is out of scope for this document as everyone's network layout and equipment will be different.

## Maintaining local access to attached services

** Note: This is not a supported configuration by Linuxserver.io - use at your own risk.

When routing via Wireguard from another container using the `service` option in docker, you might lose access to the containers webUI locally. To avoid this, exclude the docker subnet from being routed via Wireguard by modifying your `wg0.conf` like so (modifying the subnets as you require):

  ```ini
  [Interface]
  PrivateKey = <private key>
  Address = 9.8.7.6/32
  DNS = 8.8.8.8
  PostUp = DROUTE=$(ip route | grep default | awk '{print $3}'); HOMENET=192.168.0.0/16; HOMENET2=10.0.0.0/8; HOMENET3=172.16.0.0/12; ip route add $HOMENET3 via $DROUTE;ip route add $HOMENET2 via $DROUTE; ip route add $HOMENET via $DROUTE;iptables -I OUTPUT -d $HOMENET -j ACCEPT;iptables -A OUTPUT -d $HOMENET2 -j ACCEPT; iptables -A OUTPUT -d $HOMENET3 -j ACCEPT;  iptables -A OUTPUT ! -o %i -m mark ! --mark $(wg show %i fwmark) -m addrtype ! --dst-type LOCAL -j REJECT
  PreDown = DROUTE=$(ip route | grep default | awk '{print $3}'); HOMENET=192.168.0.0/16; HOMENET2=10.0.0.0/8; HOMENET3=172.16.0.0/12; ip route del $HOMENET3 via $DROUTE;ip route del $HOMENET2 via $DROUTE; ip route del $HOMENET via $DROUTE; iptables -D OUTPUT ! -o %i -m mark ! --mark $(wg show %i fwmark) -m addrtype ! --dst-type LOCAL -j REJECT; iptables -D OUTPUT -d $HOMENET -j ACCEPT; iptables -D OUTPUT -d $HOMENET2 -j ACCEPT; iptables -D OUTPUT -d $HOMENET3 -j ACCEPT
  ```

## Site-to-site VPN

** Note: This is not a supported configuration by Linuxserver.io - use at your own risk.

Site-to-site VPN in server mode requires customizing the `AllowedIPs` statement for a specific peer in `wg0.conf`. Since `wg0.conf` is autogenerated when server vars are changed, it is not recommended to edit it manually.

In order to customize the `AllowedIPs` statement for a specific peer in `wg0.conf`, you can set an env var `SERVER_ALLOWEDIPS_PEER_<peer name or number>` to the additional subnets you'd like to add, comma separated and excluding the peer IP (ie. `"192.168.1.0/24,192.168.2.0/24"`). Replace `<peer name or number>` with either the name or number of a peer (whichever is used in the `PEERS` var).

For instance `SERVER_ALLOWEDIPS_PEER_laptop="192.168.1.0/24,192.168.2.0/24"` will result in the wg0.conf entry `AllowedIPs = 10.13.13.2,192.168.1.0/24,192.168.2.0/24` for the peer named `laptop`.

Keep in mind that this var will only be considered when the confs are regenerated. Adding this var for an existing peer won't force a regeneration. You can delete wg0.conf and restart the container to force regeneration if necessary.

Don't forget to set the necessary POSTUP and POSTDOWN rules in your client's peer conf for lan access.

Image: `ghcr.io/linuxserver-playground/wireguard:latest` ([https://github.com/linuxserver-playground/docker-wireguard](https://github.com/linuxserver-playground/docker-wireguard))
