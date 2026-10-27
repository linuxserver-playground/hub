"""
A Runtipi app store: `apps/<name>/config.json`, `docker-compose.yml` in the dynamic compose format (`x-runtipi`
schema_version 2: the main service carries `is_main` and `internal_port`; Runtipi adds the port mapping, the
Traefik labels and the network itself), and `metadata/description.md`. Runtipi expects `metadata/logo.jpg` as a
file in the repository; the hub does not copy logos into git, so `logo_url` in config.json points at `docs.logo`
and the description page shows it.

Import: Runtipi > Settings > App Stores > Add App Store > `https://github.com/linuxserver-playground/runtipi-store`.
Runtipi clones a git repository and wants `apps/` at its root, so refresh.yml pushes this output to that repository
(scripts/publish_store.sh).
"""

from __future__ import annotations

from typing import Any

from .common import Files, GenerateContext, ImageInput, json_text, plain, yaml_text

Json = dict[str, Any]

CATEGORY_MAP = {
    "media": ("media", "music", "photo", "video", "book"),
    "network": ("network", "dns", "vpn", "proxy"),
    "development": ("develop", "code", "git"),
    "automation": ("automation", "home"),
    "social": ("social", "chat", "communication"),
    "security": ("security", "password", "auth"),
    "finance": ("finance", "budget"),
    "gaming": ("game",),
    "books": ("book", "comic"),
    "photography": ("photo",),
    "data": ("database", "data", "analytics"),
}


def tipi_categories(categories: list[str]) -> list[str]:
    joined = " ".join(categories).lower()
    found = [name for name, keywords in CATEGORY_MAP.items() if any(k in joined for k in keywords)]
    return found or ["utilities"]


def form_fields(image: ImageInput) -> list[Json]:
    fields = []
    for item in image.rt["env"]:
        field: Json = {
            "type": "password" if item["secret"] else "text",
            "label": item["title"] or item["name"],
            "hint": plain(item["description"]),
            "required": not item["optional"],
            "env_variable": f"{image.name.upper().replace('-', '_')}_{item['name']}",
        }
        if item["value"]:
            field["default"] = item["value"]
        if item["options"]:
            field["type"] = "text"
            field["options"] = [{"label": o, "value": o} for o in item["options"]]
        fields.append(field)
    return fields


def config(image: ImageInput) -> Json:
    port = int(image.web_port or 80)
    return {
        "name": image.title,
        "available": True,
        "exposable": True,
        "port": port,
        "id": image.name,
        "tipi_version": 1,
        "version": image.version,
        "categories": tipi_categories(image.categories),
        "description": plain(image.summary_oneline),
        "short_desc": plain(image.summary_oneline).split(". ")[0].rstrip(".")[:120],
        "author": "linuxserver.io",
        "source": image.repo_url,
        "website": image.project_url,
        "logo_url": image.logo,
        "form_fields": form_fields(image),
        "supported_architectures": image.platforms,
        "dynamic_config": False,
    }


def compose(image: ImageInput) -> Json:
    rt, name = image.rt, image.name
    port = int(image.web_port or 80)
    env: Json = {}
    for item in image.env_items():
        if item["name"] in ("PUID", "PGID"):
            env[item["name"]] = "1000"
        elif item["name"] == "TZ":
            env["TZ"] = "${TZ}"
        else:
            env[item["name"]] = f"${{{name.upper().replace('-', '_')}_{item['name']}}}"
    service: Json = {
        "image": image.image_ref,
        "environment": env,
        "volumes": [
            f"${{APP_DATA_DIR}}/data{v['path']}:{v['path']}" + (":ro" if v["mode"] == "ro" else "")
            for v in rt["volumes"]
        ],
    }
    # Runtipi maps ${APP_PORT} to internal_port itself; only the other required ports are listed.
    extra_ports = [
        f"{p['external']}:{p['internal']}"
        for p in rt["ports"]
        if not p["optional"] and p["internal"].split("/")[0] != str(port)
    ]
    if extra_ports:
        service["ports"] = extra_ports
    caps = [c["cap"] for c in rt["cap_add"] if not c["optional"]]
    if caps:
        service["cap_add"] = caps
    if rt["privileged"] is True:
        service["privileged"] = True
    service["x-runtipi"] = {"is_main": True, "internal_port": port}
    return {"services": {name: service}, "x-runtipi": {"schema_version": 2}}


def description(image: ImageInput) -> str:
    lines = [f"# {image.title}", ""]
    if image.logo:
        lines += [f"![{image.title}]({image.logo})", ""]
    lines += [image.ctx["summary"], ""]
    if image.ctx["setup"].strip():
        lines += ["## Application setup", "", image.ctx["setup"].strip(), ""]
    lines += [f"Image: `{image.image_ref}` ([{image.repo_url}]({image.repo_url}))", ""]
    return "\n".join(lines)


def generate(ctx: GenerateContext) -> Files:
    files: Files = {}
    for image in ctx.enabled("runtipi"):
        files[f"apps/{image.name}/config.json"] = json_text(config(image))
        files[f"apps/{image.name}/docker-compose.yml"] = yaml_text(compose(image))
        files[f"apps/{image.name}/metadata/description.md"] = description(image)
    return files
