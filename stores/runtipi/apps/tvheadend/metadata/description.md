# Tvheadend

![Tvheadend](https://raw.githubusercontent.com/linuxserver/docker-templates/master/linuxserver.io/img/tvheadend-big.png)

[Tvheadend](https://www.tvheadend.org/) works as a proxy server: is a TV streaming server and recorder for Linux, FreeBSD and Android supporting DVB-S, DVB-S2, DVB-C, DVB-T, ATSC, ISDB-T, IPTV, SAT>IP and HDHomeRun as input sources.
Tvheadend offers the HTTP (VLC, MPlayer), HTSP (Kodi, Movian) and SAT>IP streaming.
Multiple EPG sources are supported (over-the-air DVB and ATSC including OpenTV DVB extensions, XMLTV, PyXML).

## Application setup

The setup depends if you run the one of the stable tags or use latest. Running latest is the easiest as it has a setup wizard.

**Stable**

First thing to do is to go to Configuration --> DVB Inputs --> TV adapters and add your LNB/switch info. Then create a new network in the Networks tab and set the correct pre-defined muxes and orbital position.
Go back to the TV adapters tab and add the newly created network under universal LNB. Go back to the Networks tab and mark the network you created earlier and press the Force Scan button. Tvheadend will now scan the muxes for services.

After the scan is done, head to the Services tab and find the services you want as channels, mark them, and press map services. They should now appear under Configuration --> Channel/EPG.

**Latest**

The first thing to do is to run the setup wizard. If it doesn't pop up at first login, you can find it in Configuration --> General --> Base and click Start Wizard. This will guide you to set up the basic parts of tvheadend.

**Configuring XMLTV grabber**

To configure the XMLTV grabber, first check if your grabber is listed in Configuration --> Channel/EPG --> EPG Grabber Modules. If it's listed, you will have to configure the grabber before enabling.
Find the path in the path field of your grabber. We will use the last part. It starts with tv_grab_. Add it after /usr/bin/ in the below command. There should be no space between Usr/bin/ and the part you added.

```
docker exec -it -u abc tvheadend /usr/bin/for_you_to_fill_out --configure
```

Now follow the on-screen progress. If you get asked about cache, just accept the default. After you have configured your grabber, you can go back and enable your grabber.

If you already have a configuration file, you can add it in the .xmltv folder where you mapped the /config volume. If it's not created, create it.

**Comskip**
This container comes with Comskip for commercial flagging of recordings. This you have to add in the recording config of tvheadend.
Go to Configuration --> Recording. Change the view level to advanced in the top right corner, and add the below in the Post-processor command field.

```
/usr/bin/comskip --ini=/config/comskip/comskip.ini "%f"
```

Now comskip will run after each recording is finished. You will find comskip.ini in the comskip folder of your /config volume mapping. See the [Comskip](http://www.kaashoek.com/comskip/) homepage for tuning of the ini file.


**FFmpeg**

FFmpeg is installed in /usr/bin/ in case you need to use it with pipe.

**EPG XML file**

If you have EPG data in XML format from a supplier, you can drop it in the data folder of your /config volume mapping. If it doesn't exist, create it. Then choose the XML file grabber in Configuration --> Channel/EPG --> EPG Grabber Modules.
If you use WebGrab+Plus, choose the WebGrab+Plus XML file grabber. The XML file goes in the same path as above.
The xml file has to be named guide.xml.

For advanced setup of tvheadend, go to [Tvheadend][appurl]

**Picons**

We have added all the picons from [picons](https://github.com/picons/picons) in the folder /picons. To enable the use of these picons, add the path to the Channel icon path in Configuration --> General --> Base.
You need to enable minimum advanced view level to see the picons options.

## Additional runtime parameters

In some cases it might be necessary to start tvheadend with additional parameters, for example to enable debugging or specify webroot for reverse proxy. Be sure to have the right parameters set, as adding the wrong once might lead to the container not starting correctly.

Image: `ghcr.io/linuxserver-playground/tvheadend:latest` ([https://github.com/linuxserver-playground/docker-tvheadend](https://github.com/linuxserver-playground/docker-tvheadend))
