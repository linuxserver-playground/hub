# Xbackbone

![Xbackbone](https://raw.githubusercontent.com/SergiX44/XBackBone/master/docs/img/xbackbone.png)

[Xbackbone](https://github.com/SergiX44/XBackBone) is a simple, self-hosted, lightweight PHP file manager that support the instant sharing tool ShareX and *NIX systems. It supports uploading and displaying images, GIF, video, code, formatted text, and file downloading and uploading. Also have a web UI with multi user management, past uploads history and search support.

## Application setup

Access the WebUI at \<your-ip>:80/443. Follow the installation wizard. For more information, check out [XBackBone](https://github.com/SergiX44/XBackBone).

If you want to change the PHP max upload size you can override the php.ini file by adding options in `/config/php/php-local.ini`

Example:

```ini
  upload_max_filesize = 25M
  post_max_size = 25M
```

For reverse proxying, remember to change the `base_url` in `/config/www/xbackbone/config.php` to your domain if you initially set up the application with a local url. E.g. `'base_url' => 'https://images.yourdomain.com',`

Image: `ghcr.io/linuxserver-playground/xbackbone:latest` ([https://github.com/linuxserver-playground/docker-xbackbone](https://github.com/linuxserver-playground/docker-xbackbone))
