# Unifi-network-application

![Unifi-network-application](https://raw.githubusercontent.com/linuxserver/docker-templates/master/linuxserver.io/img/unifi-banner.png)

The [Unifi-network-application](https://ui.com/) software is a powerful, enterprise wireless software engine ideal for high-density client deployments requiring low latency and high uptime performance.

## Application setup

After setup, the web UI is available at https://ip:8443. The application can be configured, or a backup restored, using the first run wizard.

**This container requires an external mongodb database instance.**

Please note that the ports listed in this readme are not exhaustive and may change upstream, please see the [official documentation](https://help.ui.com/hc/en-us/articles/218506997-Required-Ports-Reference) for the most up-to-date list.

### Setting Up Your External Database

Starting with version 8.1 of Unifi Network Application, mongodb 3.6 through 7.0 are supported. Starting with version 9.0 of Unifi Network Application, mongodb 8.0 is also supported.

**Make sure you pin your database image version and do not use `latest`, as mongodb does not support automatic upgrades between major versions.**

**MongoDB >4.4 on X86_64 Hardware needs a CPU with AVX support. Some lower end Intel CPU models like Celeron and Pentium (before Tiger-Lake) more Details: [Advanced Vector Extensions - Wikipedia](https://en.wikipedia.org/wiki/Advanced_Vector_Extensions#CPUs_with_AVX) don't support AVX, but you can still use MongoDB 4.4.**

If you are using the [official mongodb container](https://hub.docker.com/_/mongo/), you can create your user using an `init-mongo.sh` file with the following contents (do not modify; copy/paste as is):

```sh
#!/bin/bash

if which mongosh > /dev/null 2>&1; then
  mongo_init_bin='mongosh'
else
  mongo_init_bin='mongo'
fi
"${mongo_init_bin}" <<EOF
use ${MONGO_AUTHSOURCE}
db.auth("${MONGO_INITDB_ROOT_USERNAME}", "${MONGO_INITDB_ROOT_PASSWORD}")
db.createUser({
  user: "${MONGO_USER}",
  pwd: "${MONGO_PASS}",
  roles: [
    "clusterMonitor",
    { db: "${MONGO_DBNAME}", role: "dbOwner" },
    { db: "${MONGO_DBNAME}_stat", role: "dbOwner" },
    { db: "${MONGO_DBNAME}_audit", role: "dbOwner" },
    { db: "${MONGO_DBNAME}_restore", role: "dbOwner" }
  ]
})
EOF
```

Mount the sh file into your *mongodb* container, and make sure to set the env vars below with the same values you supplied to the Unifi container.

For example:
  ```yaml
    unifi-db:
      image: docker.io/mongo:<version tag>
      container_name: unifi-db
      environment:
        - MONGO_INITDB_ROOT_USERNAME=root
        - MONGO_INITDB_ROOT_PASSWORD=
        - MONGO_USER=unifi
        - MONGO_PASS=
        - MONGO_DBNAME=unifi
        - MONGO_AUTHSOURCE=admin
      volumes:
        - /path/to/data:/data/db
        - /path/to/init-mongo.sh:/docker-entrypoint-initdb.d/init-mongo.sh:ro
      restart: unless-stopped
  ```


*Note that the init script method will only work on first run. If you start the Mongodb container without an init script it will generate test data automatically and you will have to manually create your databases, or restart with a clean `/data/db` volume and an init script mounted.*

You can also run the commands directly against the database using either `mongo` (< 6.0) or `mongosh` (>= 6.0).

### Device Adoption

For Unifi to adopt other devices, e.g. an Access Point, it is required to change the inform IP address. Because Unifi runs inside Docker by default it uses an IP address not accessible by other devices. To change this go to UniFi Devices > Device Updates and Settings > Device SSH Settings, enable Inform Host Override and set the Inform Host to a hostname or IP address accessible by your devices (devices use the inform-endpoint during adoption).

Note that you must use 8080:8080. If you MUST change the port, it must be changed on both sides and manually changed in your system.properties file. Otherwise, devices will initially communicate and then break after.

**Please note, Unifi change the location of this option every few releases so if it's not where it says, search for "Inform" or "Inform Host" in the settings.**

In order to manually adopt a device take these steps:

```
ssh ubnt@$AP-IP
set-inform http://$address:8080/inform
```

The default device password is `ubnt`. `$address` is the IP address of the host you are running this container on and `$AP-IP` is the Access Point IP address.

When using a Security Gateway (router) it could be that network connected devices are unable to obtain an ip address. This can be fixed by setting "DHCP Gateway IP", under Settings > Networks > network_name, to a correct (and accessible) ip address.

Image: `ghcr.io/linuxserver-playground/unifi-network-application:latest` ([https://github.com/linuxserver-playground/docker-unifi-network-application](https://github.com/linuxserver-playground/docker-unifi-network-application))
