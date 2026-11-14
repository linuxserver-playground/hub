# Bitcoin-knots

![Bitcoin-knots](https://raw.githubusercontent.com/linuxserver/docker-templates/master/linuxserver.io/img/bitcoin-knots-logo.png)

[Bitcoin Knots](https://bitcoinknots.org/) can be used as a desktop client for regular payments or as a full node server utility for merchants and other payment services.

## Application setup

The application can be accessed at:

* https://yourhost:3001/

>[!WARNING]
>This container is intended to run as a full Bitcoin node for the network, using it as a wallet is dangerous unless you really know what you are doing. Even momentary accidental exposure of this container can completely compromise a stored wallet.

Image: `ghcr.io/linuxserver-playground/bitcoin-knots:latest` ([https://github.com/linuxserver-playground/docker-bitcoin-knots](https://github.com/linuxserver-playground/docker-bitcoin-knots))
