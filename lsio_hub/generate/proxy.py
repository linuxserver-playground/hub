"""
SWAG reverse proxy samples from the manifest's `proxy` block, in the shape of the live
linuxserver/reverse-proxy-confs files: auth includes as comments, one location per `api_locations` entry
that bypasses auth, websocket upgrade headers when `websocket` is set, and `extra_locations`.

Import: the output is the proxy-confs repository (`<name>.subdomain.conf.sample`, `<name>.subfolder.conf.sample`,
README.md); SWAG pulls that repository into /config/nginx/proxy-confs.
"""

from __future__ import annotations

from typing import Any

from .common import Files, GenerateContext, ImageInput

Json = dict[str, Any]

AUTHS = [
    ("ldap auth", "ldap"),
    ("Authelia", "authelia"),
    ("Authentik", "authentik"),
    ("Tinyauth", "tinyauth"),
]


def _server_includes() -> list[str]:
    lines: list[str] = []
    for label, key in AUTHS:
        lines += [
            f"    # enable for {label} (requires {key}-location.conf in the location block)",
            f"    #include /config/nginx/{key}-server.conf;",
            "",
        ]
    return lines


def _location_auth(indent: str) -> list[str]:
    lines = [
        f"{indent}# enable the next two lines for http auth",
        f'{indent}#auth_basic "Restricted";',
        f"{indent}#auth_basic_user_file /config/nginx/.htpasswd;",
        "",
    ]
    for label, key in AUTHS:
        lines += [
            f"{indent}# enable for {label} (requires {key}-server.conf in the server block)",
            f"{indent}#include /config/nginx/{key}-location.conf;",
            "",
        ]
    return lines


def _upstream(indent: str, app: str, port: int, scheme: str, websocket: bool, raw: str | None) -> list[str]:
    lines = [
        f"{indent}include /config/nginx/proxy.conf;",
        f"{indent}include /config/nginx/resolver.conf;",
        f"{indent}set $upstream_app {app};",
        f"{indent}set $upstream_port {port};",
        f"{indent}set $upstream_proto {scheme};",
        f"{indent}proxy_pass $upstream_proto://$upstream_app:$upstream_port;",
        "",
    ]
    if websocket:
        lines += [
            f"{indent}proxy_set_header Upgrade $http_upgrade;",
            f'{indent}proxy_set_header Connection "upgrade";',
            "",
        ]
    if raw:
        lines += [f"{indent}{line}" if line.strip() else "" for line in raw.strip().splitlines()] + [""]
    return lines


def _version_line(image: ImageInput) -> str:
    date = image.build_date
    if date is None:
        changelog = image.ctx["changelog"]
        date = str(changelog[0]["date"]) if changelog else "2026-01-01"
    return f"## Version {date.replace('-', '/')}"


def _extra_locations(image: ImageInput, proxy: Json, indent: str, prefix: str) -> list[str]:
    lines: list[str] = []
    app = image.rt["container_name"]
    for extra in proxy.get("extra_locations", []):
        path = extra["path"]
        lines += [f"{indent}location {prefix}{path} {{"]
        if extra.get("auth", True):
            lines += _location_auth(indent + "    ")
        lines += _upstream(
            indent + "    ",
            app,
            int(extra.get("port", proxy["port"])),
            str(extra.get("scheme", proxy.get("scheme", "http"))),
            bool(proxy.get("websocket", False)),
            extra.get("raw"),
        )
        lines += [f"{indent}}}", ""]
    return lines


def subdomain(image: ImageInput) -> str:
    proxy = image.manifest["proxy"]
    app = image.rt["container_name"]
    name = image.name
    port, scheme, websocket = int(proxy["port"]), str(proxy.get("scheme", "http")), bool(proxy.get("websocket", False))
    lines = [
        _version_line(image),
        f"# make sure that your {name} container is named {app}",
        f"# make sure that your dns has a cname set for {name}",
    ]
    lines += [f"# {note}" for note in proxy.get("notes", [])]
    lines += [
        "",
        "server {",
        "    listen 443 ssl;",
        "#    listen 443 quic;",
        "    listen [::]:443 ssl;",
        "#    listen [::]:443 quic;",
        "",
        f"    server_name {name}.*;",
        "",
        "    include /config/nginx/ssl.conf;",
        "",
        "    client_max_body_size 0;",
        "",
    ]
    lines += _server_includes()
    lines += ["    location / {"]
    lines += _location_auth("        ")
    lines += _upstream("        ", app, port, scheme, websocket, None)
    lines += ["    }", ""]
    for api in proxy.get("api_locations", []):
        lines += [f"    location ~ (/{name})?{api} {{"]
        lines += _upstream("        ", app, port, scheme, websocket, None)
        lines += ["    }", ""]
    lines += _extra_locations(image, proxy, "    ", "")
    while lines and lines[-1] == "":
        lines.pop()
    lines.append("}")
    return "\n".join(lines) + "\n"


def subfolder(image: ImageInput) -> str | None:
    proxy = image.manifest["proxy"]
    folder = proxy.get("subfolder", {})
    if not folder.get("supported", False):
        return None
    app = image.rt["container_name"]
    name = image.name
    port, scheme, websocket = int(proxy["port"]), str(proxy.get("scheme", "http")), bool(proxy.get("websocket", False))
    lines = [
        _version_line(image),
        f"# make sure that your {name} container is named {app}",
        f"# make sure that {name} is set to work with the base url /{name}/",
    ]
    if folder.get("base_url_note"):
        lines.append(f"# {folder['base_url_note']}")
    lines += [f"# {note}" for note in proxy.get("notes", [])]
    lines += ["", f"location ^~ /{name} {{"]
    lines += _location_auth("    ")
    lines += _upstream("    ", app, port, scheme, websocket, None)
    lines += ["}", ""]
    for api in proxy.get("api_locations", []):
        lines += [f"location ^~ /{name}{api} {{"]
        lines += _upstream("    ", app, port, scheme, websocket, None)
        lines += ["}", ""]
    lines += _extra_locations(image, proxy, "", f"/{name}")
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines) + "\n"


README = """\
# Reverse proxy confs

Generated by the hub from the `proxy` block of every image manifest. Do not edit the `*.sample` files
here; change `image.yml` in the image repository. Samples for applications that are not LinuxServer.io
images live in `extra/` and are maintained by hand.

They are grouped in two:

1. `subfolder` samples serve an application at https://yourdomain.com/servicename
2. `subdomain` samples serve it at https://servicename.yourdomain.com

Subdomain proxying is recommended: subfolder support needs the application to cooperate.

## To enable a sample

1. Make sure the SWAG default site config includes `/config/nginx/proxy-confs/*.subdomain.conf;` (and
   `*.subfolder.conf;` for subfolder samples).
2. Put SWAG and the application on the same user-defined docker network so the container name resolves.
3. Copy the sample without its `.sample` suffix (`sonarr.subdomain.conf`) and restart SWAG.
4. Read the first lines of the file: some applications need a base URL set in their own settings.

Each sample carries commented includes for http auth, LDAP, Authelia, Authentik and Tinyauth; uncomment
the pair you use. API paths listed in the manifest bypass authentication so client applications keep working.
"""


def generate(ctx: GenerateContext) -> Files:
    files: Files = {"README.md": README}
    for image in ctx.current:
        if not image.manifest.get("proxy"):
            continue
        if image.manifest["proxy"].get("subdomain", True):
            files[f"{image.name}.subdomain.conf.sample"] = subdomain(image)
        folder = subfolder(image)
        if folder:
            files[f"{image.name}.subfolder.conf.sample"] = folder
    return files
