"""
An Umbrel community app store: `umbrel-app-store.yml` plus `lsio-<name>/umbrel-app.yml`, `docker-compose.yml`
(the app_proxy pattern, data under APP_DATA_DIR) and `exports.sh` per app.

Import: Umbrel > App Store > Community App Stores > `https://github.com/linuxserver-playground/umbrel-store`.
Umbrel clones a git repository and wants `umbrel-app-store.yml` at its root, so deploy.yml pushes this output to
that repository (scripts/publish_store.sh). Layout as the getumbrel/umbrel-community-app-store template: every app
directory is named `<store id>-<app>` and holds `umbrel-app.yml` and `docker-compose.yml`; `exports.sh` is optional.
"""

from __future__ import annotations

from typing import Any

from .common import Files, GenerateContext, ImageInput, plain, yaml_text

Json = dict[str, Any]
STORE_ID = "lsio"

CATEGORY_MAP = {
    "media": ("media", ("media", "music", "photo", "video", "book", "audio", "podcast", "comic")),
    "files": ("files", ("file", "backup", "storage", "sync", "document")),
    "networking": ("networking", ("network", "dns", "vpn", "proxy", "wireless", "web server")),
    "developer": ("developer", ("develop", "code", "git", "ci", "database")),
    "automation": ("automation", ("automation", "home", "download", "irc", "bot")),
    "social": ("social", ("social", "chat", "communication", "mail")),
    "finance": ("finance", ("finance", "budget", "bitcoin")),
    "gaming": ("gaming", ("game", "emulat")),
}


def umbrel_category(categories: list[str]) -> str:
    joined = " ".join(categories).lower()
    for name, keywords in CATEGORY_MAP.values():
        if any(k in joined for k in keywords):
            return name
    return "utilities"


def app_id(name: str) -> str:
    return f"{STORE_ID}-{name}"


def manifest(image: ImageInput) -> Json:
    port = int(image.web_port or 80)
    return {
        "manifestVersion": 1,
        "id": app_id(image.name),
        "category": umbrel_category(image.categories),
        "name": image.title,
        "tagline": plain(image.summary_oneline).split(". ")[0].rstrip(".")[:100],
        "icon": image.logo,
        "version": image.version,
        "description": plain(image.summary_oneline),
        "developer": "LinuxServer.io",
        "website": image.project_url,
        "dependencies": [],
        "repo": image.repo_url,
        "support": f"{image.repo_url}/issues",
        "port": port,
        "gallery": [],
        "releaseNotes": "",
        "path": "" if image.web_path == "/" else image.web_path,
        "defaultUsername": "",
        "defaultPassword": "",
        "submitter": "LinuxServer.io",
        "submission": image.repo_url,
    }


def compose(image: ImageInput) -> Json:
    rt, name = image.rt, image.name
    port = int(image.web_port or 80)
    env: Json = {}
    for item in image.env_items():
        env[item["name"]] = "${TZ}" if item["name"] == "TZ" else item["value"]
    service: Json = {
        "image": image.image_ref,
        "restart": "on-failure",
        "stop_grace_period": "1m",
        "environment": env,
        "volumes": [
            f"${{APP_DATA_DIR}}/data{v['path']}:{v['path']}" + (":ro" if v["mode"] == "ro" else "")
            for v in rt["volumes"]
        ],
    }
    caps = [c["cap"] for c in rt["cap_add"] if not c["optional"]]
    if caps:
        service["cap_add"] = caps
    if rt["privileged"] is True:
        service["privileged"] = True
    extra_ports = [
        f"{p['external']}:{p['internal']}"
        for p in rt["ports"]
        if not p["optional"] and p["internal"].split("/")[0] != str(port)
    ]
    if extra_ports:
        service["ports"] = extra_ports
    return {
        "version": "3.7",
        "services": {
            "app_proxy": {"environment": {"APP_HOST": f"{app_id(name)}_server_1", "APP_PORT": port}},
            "server": service,
        },
    }


def exports(image: ImageInput) -> str:
    prefix = f"APP_{image.name.upper().replace('-', '_')}"
    lines = [f'export {prefix}_PORT="{image.web_port or 80}"', f'export {prefix}_IMAGE="{image.image_ref}"']
    return "\n".join(lines) + "\n"


def generate(ctx: GenerateContext) -> Files:
    files: Files = {"umbrel-app-store.yml": yaml_text({"id": STORE_ID, "name": "LinuxServer.io"})}
    for image in ctx.enabled("umbrel"):
        folder = app_id(image.name)
        files[f"{folder}/umbrel-app.yml"] = yaml_text(manifest(image))
        files[f"{folder}/docker-compose.yml"] = yaml_text(compose(image))
        files[f"{folder}/exports.sh"] = exports(image)
    return files
