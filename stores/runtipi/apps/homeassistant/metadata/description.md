# Homeassistant

![Homeassistant](https://github.com/home-assistant/home-assistant.io/raw/next/source/images/favicon-192x192-full.png)

[Home Assistant Core](https://www.home-assistant.io/) - Open source home automation that puts local control and privacy first. Powered by a worldwide community of tinkerers and DIY enthusiasts. Perfect to run on a Raspberry Pi or a local server

## Application setup

This image is based on Home Assistant Core.

The Webui can be found at `http://your-ip:8123`. Follow the wizard to set up Home Assistant.

### Host vs. Bridge

Home Assistant can [discover][hb0] and automatically configure
[zeroconf][hb1]/[mDNS][hb2] and [UPnP][hb3] devices on your network. In
order for this to work you must create the container with `--net=host`.

[hb0]: https://www.home-assistant.io/integrations/discovery/#mdns-and-upnp
[hb1]: https://en.wikipedia.org/wiki/Zero-configuration_networking
[hb2]: https://en.wikipedia.org/wiki/Multicast_DNS
[hb3]: https://en.wikipedia.org/wiki/Universal_Plug_and_Play

### Accessing Bluetooth Device

In order to provide HA with access to the host's Bluetooth device, one needs to install BlueZ on the host, add the capabilities `NET_ADMIN` and `NET_RAW` to the container, and map dbus as a volume as shown in the below examples.

#### Docker Cli:
```bash
--cap-add=NET_ADMIN --cap-add=NET_RAW -v /run/dbus:/run/dbus:ro
```

#### Docker Compose:
```yaml
    cap_add:
      - NET_ADMIN
      - NET_RAW
    volumes:
      - /run/dbus:/run/dbus:ro
```

If the dbus path on host differs, such as `/var/run/dbus`, then you can map it as `/var/run/dbus:/run/dbus:ro`.

### Using the Ping integration

For the [Ping][ping0] integration to work, the capability `NET_RAW` must be added to the container. See above for instructions.

[ping0]: https://www.home-assistant.io/integrations/ping

Image: `ghcr.io/linuxserver-playground/homeassistant:latest` ([https://github.com/linuxserver-playground/docker-homeassistant](https://github.com/linuxserver-playground/docker-homeassistant))
