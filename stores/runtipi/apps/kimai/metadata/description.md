# Kimai

![Kimai](https://raw.githubusercontent.com/linuxserver/docker-templates/master/linuxserver.io/img/kimai-logo.png)

[Kimai](https://kimai.org/) is a professional grade time-tracking application, free and open-source.
It handles use-cases of freelancers as well as companies with dozens or hundreds of users.
Kimai was build to track your project times and ships with many advanced features, including but not limited to:

JSON API, invoicing, data exports, multi-timer and punch-in punch-out mode, tagging, multi-user - multi-timezones - multi-language ([over 30 translations existing](https://hosted.weblate.org/projects/kimai/)!), authentication via SAML/LDAP/Database, two-factor authentication (2FA) with TOTP, customizable role and team permissions, responsive design, user/customer/project specific rates, advanced search & filtering, money and time budgets, advanced reporting, support for [plugins](https://www.kimai.org/store/) and so much more.

## Application setup

### Configure your database connection

You have to replace the following values with your defaults:

* the database username "your_db_user"
* the database password "your_db_pass"
* the database schema name "your_db_name"
* the database host or IP "your_db_host"
* the database character set "your_db_charset" (usually "utf8")
* the database version "your_db_version"
  * run `SELECT VERSION();` in your MariaDB/MySQL database to get the version
  * example for [MariaDB](https://www.doctrine-project.org/projects/doctrine-dbal/en/current/reference/configuration.html#mariadb) use "10.11.4-MariaDB-log"
  * example for [MySQL](https://www.doctrine-project.org/projects/doctrine-dbal/en/current/reference/configuration.html#mysql) use "8.0.32"
* you might have to adapt port "3306" as well

```env
DATABASE_URL=mysql://your_db_user:your_db_pass@your_db_host:3306/your_db_name?charset=your_db_charset&serverVersion=your_db_version
````

### Create your first user

```shell
docker exec -it kimai console kimai:user:create your_username admin@example.com ROLE_SUPER_ADMIN
```

### Initial setup

Access the web gui at `http://<your-ip>:80`, for more information check out [Kimai Initial setup](https://www.kimai.org/documentation/initial-setup.html).

Image: `ghcr.io/linuxserver-playground/kimai:latest` ([https://github.com/linuxserver-playground/docker-kimai](https://github.com/linuxserver-playground/docker-kimai))
