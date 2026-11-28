# Lychee

![Lychee](https://raw.githubusercontent.com/linuxserver/docker-templates/master/linuxserver.io/img/lychee-icon.png)

[Lychee](https://lycheeorg.github.io/) is a free photo-management tool, which runs on your server or web-space. Installing is a matter of seconds. Upload, manage and share photos like from a native application. Lychee comes with everything you need and all your photos are stored securely.

## Application setup

**This image will not work with a prefilled `/pictures` mount, Lychee wants total control over this folder**

Setup account via the webui, accessible at http://SERVERIP:PORT

More info at [lychee](https://lycheeorg.github.io/).

### Customization

In certain scenarios, you might need to change the default settings of Lychee. For instance, if you encounter limitations when uploading large files, you can increase this limit.

#### Increasing Upload Limit

The upload limit is defined in the `user.ini` file located in the config directory (`/config`). You can increase this limit by modifying the following values:

```ini
post_max_size = 500M
upload_max_filesize = 500M
```

After making these changes, you'll need to restart the Docker container for the changes to take effect.

**Please note that these changes might have implications on your server's performance, depending on its available resources. Thus, it's recommended to modify these settings with caution.**

Image: `ghcr.io/linuxserver-playground/lychee:latest` ([https://github.com/linuxserver-playground/docker-lychee](https://github.com/linuxserver-playground/docker-lychee))
