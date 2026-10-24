"""
A Runtipi app store: `apps/<name>/config.json`, `docker-compose.yml` with `x-runtipi` metadata, and
`metadata/description.md`. Runtipi expects `metadata/logo.jpg` as a file in the repository; the hub does not
copy logos into git, so `logo_url` in config.json points at `docs.logo` and the description page shows it.

Import: Runtipi > Settings > App Stores > `https://github.com/linuxserver-playground/stores` with the
`runtipi/` folder as the store root (Runtipi clones a git repository).
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
        "$schema": "../schema.json",
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
        "container_name": name,
        "restart": "unless-stopped",
        "environment": env,
        "volumes": [
            f"${{APP_DATA_DIR}}/data{v['path']}:{v['path']}" + (":ro" if v["mode"] == "ro" else "")
            for v in rt["volumes"]
        ],
        "ports": [f"${{APP_PORT}}:{port}"],
        "networks": ["tipi_main_network"],
        "labels": {
            "traefik.enable": "true",
            f"traefik.http.services.{name}.loadbalancer.server.port": str(port),
            f"traefik.http.routers.{name}-insecure.rule": "Host(`${APP_DOMAIN}`)",
            f"traefik.http.routers.{name}-insecure.entrypoints": "web",
            f"traefik.http.routers.{name}-insecure.service": name,
            f"traefik.http.routers.{name}-insecure.middlewares": "redirect-to-https",
            f"traefik.http.routers.{name}.rule": "Host(`${APP_DOMAIN}`)",
            f"traefik.http.routers.{name}.entrypoints": "websecure",
            f"traefik.http.routers.{name}.service": name,
            f"traefik.http.routers.{name}.tls.certresolver": "myresolver",
            "runtipi.managed": "true",
        },
    }
    caps = [c["cap"] for c in rt["cap_add"] if not c["optional"]]
    if caps:
        service["cap_add"] = caps
    if rt["privileged"] is True:
        service["privileged"] = True
    return {
        "x-runtipi": {"schema_version": 2, "main_service": name, "internal_port": port, "image_source": image.repo_url},
        "services": {name: service},
        "networks": {"tipi_main_network": {"external": True}},
    }


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
