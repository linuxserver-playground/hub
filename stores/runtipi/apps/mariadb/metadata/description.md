# Mariadb

![Mariadb](https://raw.githubusercontent.com/linuxserver/docker-templates/master/linuxserver.io/img/mariadb-git.png)

[Mariadb](https://mariadb.org/) is one of the most popular database servers. Made by the original developers of MySQL.

## Application setup

Root via localhost (docker exec) no longer requires a password according to [upstream behavior](https://mariadb.com/docs/server/security/user-account-management/authentication-from-mariadb-10-4), if you didn't set a root password for remote access during the initial start follow the instructions in the container log.

NOTE changing any of the MYSQL_ variables after the container has set up the initial databases has no effect, use the mysqladmin tool or cli to make changes.

NOTE if you want to use (MYSQL_DATABASE MYSQL_USER MYSQL_PASSWORD) **all three** of these variables need to be set you cannot pick and choose.

Unraid users, it is advisable to edit the template/webui after setup and remove reference to this variable.

Find custom.cnf in /config for config changes (restart container for them to take effect)
, the databases in /config/databases and the log in /config/log/myqsl

### Loading passwords and users from files

The `MYSQL_ROOT_PASSWORD MYSQL_DATABASE MYSQL_USER MYSQL_PASSWORD REMOTE_SQL` env values can be set in a file:

```path
/config/env
```

Using the following format:

```env
MYSQL_ROOT_PASSWORD="ROOT_ACCESS_PASSWORD"
MYSQL_DATABASE="USER_DB_NAME"
MYSQL_USER="MYSQL_USER"
MYSQL_PASSWORD="DATABASE_PASSWORD"
REMOTE_SQL="http://URL1/your.sql,https://URL2/your.sql"
```

These settings can be mixed and matched with Docker ENV settings as you require, but the settings in the file will always take precedence.

### Bootstrapping a new instance

We support a one time run of custom sql files on init. In order to use this place `*.sql` files in:

```path
/config/initdb.d/
```
This will have the same effect as setting the `REMOTE_SQL` environment variable. The sql will only be run on the containers first boot and setup.

### Check and Repair

If user databases are not in a healthy state (sometimes caused by a failed upgrade), it may be remedied by running:

```shell
mariadb-check -c -A # check all databases for errors
mariadb-check -r -A # repair all databases
mariadb-check -a -A # analyze all databases
mariadb-check -o -A # optimize all databases
```

After running the above commands, you may need to run the upgrade command again.

### Upgrading

When this container initializes, if `MYSQL_ROOT_PASSWORD` is set an upgrade check will run. If an upgrade is required the log will indicate the need stop any services that are accessing databases in this container, and then run the command:

```shell
mariadb-upgrade
```

Image: `ghcr.io/linuxserver-playground/mariadb:latest` ([https://github.com/linuxserver-playground/docker-mariadb](https://github.com/linuxserver-playground/docker-mariadb))
