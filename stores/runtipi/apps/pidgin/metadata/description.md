# Pidgin

![Pidgin](https://raw.githubusercontent.com/linuxserver/docker-templates/master/linuxserver.io/img/pidgin-logo.png)

[Pidgin](https://pidgin.im/) is a chat program which lets you log into accounts on multiple chat networks simultaneously. This means that you can be chatting with friends on XMPP and sitting in an IRC channel at the same time.

## Application setup

The application can be accessed at:

* https://yourhost:3001/

This Pidgin installation comes with default chat plugins plus a series of third party ones. **Please note that the third party plugins for the most part are not simply plug and play, you will need to reference their documentation and possibly generate oauth tokens along with other workarounds**. Third party plugins are always in a state of constant development do not expect every single native feature to work flawlessly. To ease integration with some third party plugins we include Firefox in this image to allow you to fill out captchas or pre-auth before loading your credentials into the program, simply right click the desktop to launch it.

* Bonjour- Default XMPP style plugin
* Discord- Provided by [purple-discord](https://github.com/EionRobb/purple-discord)
* Facebook- Provided by [purple-facebook](https://github.com/dequis/purple-facebook)
* Gadu-Gadu- Default libgadu plugin
* Google Talk- Provided by [purple-hangouts](https://github.com/EionRobb/purple-hangouts)
* GroupWise- Default GroupWise plugin
* Hangouts- Provided by [purple-hangouts](https://github.com/EionRobb/purple-hangouts)
* ICQ (WIM)- Provided by [icyque](https://github.com/EionRobb/icyque)
* IRC- Default IRC plugin
* Instagram- Provided by [purple-instagram](https://github.com/EionRobb/purple-instagram)
* Office Comminicator (SIPE)- Provided by [SIPE Project](https://sipe.sourceforge.io/)
* Rocket.chat- Provided by [purple-rocketchat](https://github.com/EionRobb/purple-rocketchat)
* SIMPLE- Default plugin
* Skype (HTTP)- Provided by [skype4pidgin](https://github.com/EionRobb/skype4pidgin)
* Slack- Provided by [slack-libpurple](https://github.com/EionRobb/slack-libpurple)
* Telegram- Provided by [telegram-purple](https://github.com/majn/telegram-purple)
* XMPP- Default XMPP plugin
* Zephyr- Default project Athena plugin

Image: `ghcr.io/linuxserver-playground/pidgin:latest` ([https://github.com/linuxserver-playground/docker-pidgin](https://github.com/linuxserver-playground/docker-pidgin))
