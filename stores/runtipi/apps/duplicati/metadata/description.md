# Duplicati

![Duplicati](https://github.com/linuxserver/docker-templates/raw/master/linuxserver.io/img/duplicati-icon.png)

[Duplicati](https://www.duplicati.com/) is a backup client that securely stores encrypted, incremental, compressed backups on local storage, cloud storage services and remote file servers. It works with standard protocols like FTP, SSH, WebDAV as well as popular services like Microsoft OneDrive, Amazon S3, Google Drive, box.com, Mega, B2, and many others.

## Application setup

The webui is at `<your ip>:8200`.

For local backups select `/backups` as the destination. For more information see [Duplicati](https://www.duplicati.com/).

Image: `ghcr.io/linuxserver-playground/duplicati:latest` ([https://github.com/linuxserver-playground/docker-duplicati](https://github.com/linuxserver-playground/docker-duplicati))
