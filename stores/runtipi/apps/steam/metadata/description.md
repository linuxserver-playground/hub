# Steam

![Steam](https://raw.githubusercontent.com/linuxserver/docker-templates/master/linuxserver.io/img/steam-logo.png)

[Steam](https://store.steampowered.com/) is the ultimate destination for playing, discussing, and creating games.

## Application setup

The application can be accessed at:

* https://yourhost:3001/

>[!NOTE]
>This image is for a web accessible version of Steam to be played through a web browser, if you want a fully flushed out Moonlight couch solution please consider [Wolf](https://games-on-whales.github.io/wolf/stable/user/quickstart.html) or another non Docker solution. Moonlight clients have major advantages over using a web browser specifically for gaming.

## Permissions

Steam runs its browser helper and every game inside [bubblewrap](https://github.com/containers/bubblewrap), which needs user namespaces. Docker's default seccomp profile (and AppArmor on Debian/Ubuntu hosts) blocks those, so the recommended way to run this container is with `--security-opt seccomp=unconfined` and `--security-opt apparmor=unconfined`, which lets Steam use bubblewrap as intended.

These options are not required, but running without them will degrade performance as userspace proot with ptrace or fakechroot will be used to run games. [proot-bwrap](https://github.com/selkies-project/proot-bwrap)

## Gamepad support

This container leverages a userspace gamepad interposer to provide gamepad support. To use a gamepad always force Proton in "Properties>Compatibility" even for Linux native games, "Proton Hotfix" is a good default selection. You cannot use the "Steam Input" feature on any game as the uinput socket and HID do not exist.

## Gaming mode

An absolute must for mouse and keyboard input is sending relative mouse input from the browser, you will need to use the "Gaming Mode" which is a small crosshair in the top right of the sidebar. This runs in fullscreen and traps you in the window, to exit this mode hold down escape for 3 seconds.

## Game Launching

Included in this image are tools for managing [Proton versions](https://davidotek.github.io/protonup-qt/) and a [command line launcher](https://github.com/Open-Wine-Components/umu-launcher). This means once a game or application is installed via Steam it can be directly launched on init by creating a config file and modifying `/config/.config/labwc/autostart` to run `umu-run` instead of Steam.:

```
umu-run --config /config/game.toml
```

```toml
[umu]
prefix = "/config/game"
exe = "/config/Desktop/game/game.exe"
proton = "/config/.local/share/Steam/compatibilitytools.d/GE-Proton-version"
game_id = "0"
```

This facilitates custom home directories with pre-configured runtimes and gamefiles for baking images outside of using the Steam launcher.

Image: `ghcr.io/linuxserver-playground/steam:latest` ([https://github.com/linuxserver-playground/docker-steam](https://github.com/linuxserver-playground/docker-steam))
