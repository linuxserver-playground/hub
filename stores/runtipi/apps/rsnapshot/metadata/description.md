# Rsnapshot

![Rsnapshot](https://raw.githubusercontent.com/linuxserver/docker-templates/master/linuxserver.io/img/rsnapshot.png)

[Rsnapshot](http://www.rsnapshot.org/) is a filesystem snapshot utility based on rsync. rsnapshot makes it easy to make periodic snapshots of local machines, and remote machines over ssh. The code makes extensive use of hard links whenever possible, to greatly reduce the disk space required.

## Application setup

### IMPORTANT NOTES:
After starting the container you will need to edit `/config/rsnapshot.conf`.

#### SNAPSHOT ROOT DIRECTORY

rsnapshot is configured to backup data to the `/.snapshots` volume by default.
This can be changed in the config, but be sure you mount a volume to the container to match.

#### BACKUP LEVELS / INTERVALS

rsnapshot retains backups based on configurations in this section.
Please see the [rsnapshot readme](https://github.com/rsnapshot/rsnapshot/blob/master/README.md#configuration) for more information.

#### BACKUP POINTS

rsnapshot is configured to backup data from the `/data` volume by default.
This can be changed in the config, but be sure you mount a volume to the container to match.

### cron

You will then need to edit `/config/crontabs/root` to set cron jobs to run rsnapshot.
By default no cron jobs are enabled. Examples are includes based on information from the [rsnapshot readme](https://github.com/rsnapshot/rsnapshot/blob/master/README.md#configuration).

Image: `ghcr.io/linuxserver-playground/rsnapshot:latest` ([https://github.com/linuxserver-playground/docker-rsnapshot](https://github.com/linuxserver-playground/docker-rsnapshot))
