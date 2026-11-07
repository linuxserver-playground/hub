# Diskover

![Diskover](https://raw.githubusercontent.com/diskoverdata/diskover-community/master/diskover-web/public/images/diskover.png)

[diskover](https://github.com/diskoverdata/diskover-community) is an open source file system indexer that uses Elasticsearch to index and manage data across heterogeneous storage systems.

## Application setup

This application is dependent on an ElasticSearch instance. Please see the example compose file for additional information.

The default username is diskover with the password of **darkdata**, access the container at `http://<host-ip>/`. The UI may be unusable until a valid index has been created.

The default diskover-web Constants.php file located at `/config/diskover-web.conf.d/Constants.php` will need to be edited to allow diskover-web to communicate with the ElasticSearch container. The following entries will need to be edited:
* `const ES_HOST = 'elasticsearch';`
* `const ES_PORT = 9200;`

The application doesn't start an index by default. A crontab is created inside of the `/config` directory and can be set up to run automated indexes of `/data`. Changes to this crontab file require a restart to apply. You can also manually run an index by executing `/app/diskover/diskover.py` either in interactive or detached mode:

* `docker exec -u abc -d diskover python3 /app/diskover/diskover.py -i diskover-my_index_name /data` Will run an index in the background
* `docker exec -u abc -it diskover python3 /app/diskover/diskover.py -i diskover-my_index_name /data` Will run an index in the foreground

Image: `ghcr.io/linuxserver-playground/diskover:latest` ([https://github.com/linuxserver-playground/docker-diskover](https://github.com/linuxserver-playground/docker-diskover))
