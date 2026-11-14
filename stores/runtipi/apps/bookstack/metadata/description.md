# Bookstack

![Bookstack](https://raw.githubusercontent.com/linuxserver/docker-templates/master/linuxserver.io/img/bookstack-logo.png)

[Bookstack](https://codeberg.org/bookstack/bookstack) is a free and open source Wiki designed for creating beautiful documentation. Featuring a simple, but powerful WYSIWYG editor it allows for teams to create detailed and useful documentation with ease.

Powered by SQL and including a Markdown editor for those who prefer it, BookStack is geared towards making documentation more of a pleasure than a chore.

For more information on BookStack visit their website and check it out: https://www.bookstackapp.com

## Application setup

The default username is admin@admin.com with the password of **password**, access the container at http://<host ip>:6875.

This application is dependent on a MariaDB database, be it one you already have or a new one. If you do not already have one, we provide an image here https://github.com/linuxserver/docker-mariadb.

If you intend to use this application behind a subfolder reverse proxy, such as our SWAG container or Traefik you will need to make sure that the `APP_URL` environment variable is set to your external domain, or it will not work.

Documentation for BookStack can be found at https://www.bookstackapp.com/docs/.

### BookStack File & Directory Paths

This container ensures certain BookStack application files & folders, such as user file upload folders, are retained within the `/config` folder so that they are persistent & accessible when the `/config` container path is bound as a volume. There may be cases, when following the BookStack documentation, that you'll need to know how these files and folders are used relative to a non-container BookStack installation.

Below is a mapping of container `/config` paths to those relative within a BookStack install directory:

- **/config container path** => **BookStack relative path**
- `/config/www/.env` => `.env`
- `/config/log/bookstack/laravel.log` => `storage/logs/laravel.log`
- `/config/backups/` => `storage/backups/`
- `/config/www/files/` => `storage/uploads/files/`
- `/config/www/images/` => `storage/uploads/images/`
- `/config/www/themes/` => `themes/`
- `/config/www/uploads/` => `public/uploads/`

### Changing APP_URL

If you change the APP_URL after initial install, you should run the following line from your host terminal to update the database URL entries:

```shell
docker exec -it bookstack php /app/www/artisan bookstack:update-url ${OLD_URL} ${NEW_URL}
```

### Advanced Users (full control over the .env file)

If you wish to use the extra functionality of BookStack such as email, LDAP and so on you will need to set additional environment variables or make your own .env file with guidance from the BookStack documentation.

The container will copy an exemplary .env file to /config/www/.env on your host system for you to use.

Image: `ghcr.io/linuxserver-playground/bookstack:latest` ([https://github.com/linuxserver-playground/docker-bookstack](https://github.com/linuxserver-playground/docker-bookstack))
