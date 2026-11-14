# Babybuddy

![Babybuddy](https://github.com/linuxserver/docker-templates/raw/master/linuxserver.io/img/babybuddy-logo.png)

[Babybuddy](https://github.com/babybuddy/babybuddy) is a buddy for babies! Helps caregivers track sleep, feedings, diaper changes, tummy time and more to learn about and predict baby's needs without (as much) guess work.

## Application setup

Access the webui at `<your-ip>:8000` (or whichever host port is mapped in docker arguments). The default user/pass are `admin:admin`.

By default BabyBuddy uses sqlite3. To use an external database like postgresql or mysql/mariadb instead, you can use the environment variables listed in [BabyBuddy docs](https://github.com/babybuddy/babybuddy#configuration).

Image: `ghcr.io/linuxserver-playground/babybuddy:latest` ([https://github.com/linuxserver-playground/docker-babybuddy](https://github.com/linuxserver-playground/docker-babybuddy))
