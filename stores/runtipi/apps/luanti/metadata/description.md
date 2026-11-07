# Luanti

![Luanti](https://raw.githubusercontent.com/linuxserver/docker-templates/master/linuxserver.io/img/minetest-icon.png)

[Luanti](https://www.luanti.org/) (formerly Minetest) is an open source voxel game-creation platform with easy modding and game creation

## Application setup

You can find the world maps, mods folder and config files in /config/.minetest.

If you want to override the advertised port, ensure you add --port in your CLI_ARGS AND ensure the internal port reflects the change, ie;
if you set your advertised port to 40000 with --port 40000 then your ports declaration should be 40000:40000/udp

Client and server must be the same version, please browse the tags here to pull the appropriate version for your server:

https://hub.docker.com/r/linuxserver/luanti/tags

### Bundled Games

As per [upstream request](https://github.com/luanti-org/luanti/releases/tag/5.8.0) this image no longer includes [minetest_game](https://github.com/luanti-org/minetest_game), so if required you will need to either install via ContentDB or download it from their repo and copy to `/config/.minetest/games/minetest`

Image: `ghcr.io/linuxserver-playground/luanti:latest` ([https://github.com/linuxserver-playground/docker-luanti](https://github.com/linuxserver-playground/docker-luanti))
