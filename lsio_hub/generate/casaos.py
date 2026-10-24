"""
A CasaOS app store: one folder per app with a docker-compose.yml carrying the `x-casaos` metadata CasaOS
reads, plus a zip of the whole store.

Import: CasaOS > App Store > More Apps > Add Source: `https://<hub>/stores/casaos/linuxserver.zip`.
"""

from __future__ import annotations

import io
import zipfile
from typing import Any

from .common import Files, GenerateContext, ImageInput, plain, yaml_text

Json = dict[str, Any]
STORE_NAME = "linuxserver"


def compose(image: ImageInput) -> Json:
    rt, name = image.rt, image.name
    service: Json = {"image": image.image_ref, "container_name": name, "restart": "unless-stopped"}
    if rt["network"] and not rt["network"]["optional"]:
        service["network_mode"] = rt["network"]["mode"]
    if rt["privileged"] is True:
        service["privileged"] = True
    caps = [c["cap"] for c in rt["cap_add"] if not c["optional"]]
    if caps:
        service["cap_add"] = caps
    env_items = image.env_items()
    service["environment"] = [f"{e['name']}={e['value']}" for e in env_items]
    volumes = [
        f"/DATA/AppData/{name}{v['path']}:{v['path']}" + (":ro" if v["mode"] == "ro" else "") for v in rt["volumes"]
    ]
    if volumes:
        service["volumes"] = volumes
    ports = [f"{p['external']}:{p['internal']}" for p in rt["ports"]] if not service.get("network_mode") else []
    if ports:
        service["ports"] = ports
    devices = [f"{d['host_path']}:{d['path']}" for d in rt["devices"] if not d["optional"]]
    if devices:
        service["devices"] = devices
    service["x-casaos"] = {
        "envs": [{"container": e["name"], "description": {"en_us": plain(e["description"])}} for e in env_items],
        "ports": [
            {"container": p["internal"].split("/")[0], "description": {"en_us": plain(p["description"])}}
            for p in rt["ports"]
        ],
        "volumes": [{"container": v["path"], "description": {"en_us": plain(v["description"])}} for v in rt["volumes"]],
    }
    port = image.web_port
    meta: Json = {
        "architectures": image.platforms,
        "main": name,
        "author": "LinuxServer.io",
        "developer": image.title,
        "category": image.categories[0],
        "description": {"en_us": plain(image.summary_oneline)},
        "tagline": {"en_us": plain(image.summary_oneline).split(". ")[0].rstrip(".")},
        "title": {"en_us": image.title},
        "icon": image.logo,
        "thumbnail": image.logo,
        "store_app_id": name,
        "index": image.web_path,
        "scheme": image.web_scheme,
    }
    if port:
        meta["port_map"] = port
    return {"name": name, "services": {name: service}, "x-casaos": meta}


def generate(ctx: GenerateContext) -> Files:
    files: Files = {}
    for image in ctx.enabled("casaos"):
        files[f"Apps/{image.name}/docker-compose.yml"] = yaml_text(compose(image))
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(files):
            info = zipfile.ZipInfo(path, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            content = files[path]
            archive.writestr(info, content.encode() if isinstance(content, str) else content)
    files[f"{STORE_NAME}.zip"] = buffer.getvalue()
    return files
