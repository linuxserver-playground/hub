# Librespeed

![Librespeed](https://raw.githubusercontent.com/librespeed/speedtest/master/.logo/logo3.png)

[Librespeed](https://github.com/librespeed/speedtest) is a very lightweight Speedtest implemented in Javascript, using XMLHttpRequest and Web Workers.

No Flash, No Java, No Websocket, No Bullshit.

## Application setup

Access the speedtest webui at `http://SERVERIP`. The results database can be accessed at `http://SERVERIP/results/stats.php` with the password set.
The default template used is based on `example-singleServer-full.html`. However, all templates are provided for reference at `/config/www/`. Feel free to customize `/config/www/index.html` as you like. Delete the file and restart to go back to the image default.

You can optionally place customized `speedtest.js` and `speedtest_worker.js` files under `/config/www` and they will supersede the defaults after a container start. Keep in mind that once you do so, they will no longer be updated. You can delete them and recreate the container to go back to the image defaults.

If you are setting up a mysql or postgresql database, you first need to import the tables into your database as described at the following link
https://github.com/librespeed/speedtest/blob/master/doc.md#creating-the-database

To enable a custom results page set the environment variable `CUSTOM_RESULTS=true` and start (or restart) the container at least once for `/config/www/results/index.php` to be created and modify this file to your liking.

Image: `ghcr.io/linuxserver-playground/librespeed:latest` ([https://github.com/linuxserver-playground/docker-librespeed](https://github.com/linuxserver-playground/docker-librespeed))
