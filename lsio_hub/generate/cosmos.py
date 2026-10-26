"""
A Cosmos Cloud market source in the format of the TinyActive community source (https://cosmos.manhtuong.net):
`index.json` with `source`, `showcase` and `all`, and per app `servapps/<name>/description.json` plus
`cosmos-compose.json` using Cosmos's `{ServiceName}` templating and an installer form for the variables.

Import: Cosmos > Market > Sources > add `https://<hub>/stores/cosmos/index.json`.
"""

from __future__ import annotations

from typing import Any

from .common import Files, GenerateContext, ImageInput, json_text, plain

Json = dict[str, Any]


def description(image: ImageInput, root: str) -> Json:
    return {
        "name": image.title,
        "longDescription": f"<p>{plain(image.ctx['summary'])}</p>",
        "description": plain(image.summary_oneline),
        "tags": sorted({image.name, *[c.lower() for c in image.categories], "linuxserver"}),
        "repository": image.repo_url,
        "image": f"https://github.com/orgs/{image.ctx['org']}/packages/container/package/{image.name}",
        "supported_architectures": image.platforms,
        "id": image.name,
        "screenshots": [image.screenshot] if image.screenshot else [],
        "logo": [],
        "icon": image.logo,
        "artefacts": {},
        "compose": f"{root}/servapps/{image.name}/cosmos-compose.json",
    }


def compose(image: ImageInput) -> Json:
    rt, name = image.rt, image.name
    port = image.web_port
    form = []
    environment = []
    for item in image.env_items():
        if item["name"] in ("PUID", "PGID", "TZ"):
            environment.append(f"{item['name']}={item['value']}")
            continue
        form.append(
            {
                "name": item["name"],
                "label": plain(item["description"]) or item["name"],
                "initialValue": item["value"],
                "type": "password" if item["secret"] else "text",
            }
        )
        environment.append(f"{item['name']}={{Context.{item['name']}}}")
    service: Json = {
        "image": image.image_ref,
        "container_name": "{ServiceName}",
        "environment": environment,
        "labels": {
            "cosmos-force-network-secured": "true",
            "cosmos-auto-update": "true",
            "cosmos-icon": image.logo,
            "cosmos.stack": f"{{ServiceName}}-{name}",
        },
        "volumes": [
            {
                "source": f"{{ServiceName}}-{v['path'].strip('/').replace('/', '-') or 'data'}",
                "target": v["path"],
                "type": "volume",
            }
            for v in rt["volumes"]
        ],
        "restart": "unless-stopped",
    }
    caps = [c["cap"] for c in rt["cap_add"] if not c["optional"]]
    if caps:
        service["cap_add"] = caps
    if rt["privileged"] is True:
        service["privileged"] = True
    if port:
        service["routes"] = [
            {
                "name": "{ServiceName}",
                "description": "Expose {ServiceName} to the web",
                "useHost": True,
                "target": f"{image.web_scheme}://{{ServiceName}}:{port}",
                "mode": "SERVAPP",
                "Timeout": 14400000,
                "ThrottlePerMinute": 12000,
                "BlockCommonBots": True,
                "SmartShield": {"Enabled": True},
            }
        ]
    out: Json = {"minVersion": "0.8.0", "services": {"{ServiceName}": service}}
    if form:
        out = {"cosmos-installer": {"form": form}, **out}
    return out


def generate(ctx: GenerateContext) -> Files:
    root = f"{ctx.site.stores_root}/cosmos"
    files: Files = {}
    apps = []
    for image in ctx.enabled("cosmos"):
        apps.append(description(image, root))
        files[f"servapps/{image.name}/description.json"] = json_text(apps[-1])
        files[f"servapps/{image.name}/cosmos-compose.json"] = json_text(compose(image))
    files["index.json"] = json_text({"source": f"{root}/index.json", "showcase": [], "all": apps})
    files["servapps.json"] = json_text(apps)
    return files
