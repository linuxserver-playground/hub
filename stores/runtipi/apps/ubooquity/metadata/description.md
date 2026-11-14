# Ubooquity

![Ubooquity](https://raw.githubusercontent.com/linuxserver/docker-templates/master/linuxserver.io/img/ubooquity-banner.png)

[Ubooquity](https://vaemendis.net/ubooquity/) is a free, lightweight and easy-to-use home server for your comics and ebooks. Use it to access your files from anywhere, with a tablet, an e-reader, a phone or a computer.

## Application setup

Access the admin page at `http://<your-ip>:2203/ubooquity/admin` and set a password.

Then you can access the webui at `http://<your-ip>:2202/ubooquity/`

This container will automatically scan your files at startup.

### MAXMEM

The quantity of memory allocated to Ubooquity depends on the hardware your are running it on. If this quantity is too small, you might sometime saturate it with when performing memory intensive operations. That’s when you get `java.lang.OutOfMemoryError:` Java heap space errors.

You can explicitly set the amount of memory Ubooquity is allowed to use (be careful to set a value lower than the actual physical memory of your hardware). Value is a number of megabytes ( put just a number, without MB )

If no value is set it will default to 512MB.

Image: `ghcr.io/linuxserver-playground/ubooquity:latest` ([https://github.com/linuxserver-playground/docker-ubooquity](https://github.com/linuxserver-playground/docker-ubooquity))
