"""
Portainer app templates, format version 3: one type 1 (container) template per image.

Import: Portainer > Settings > App Templates > URL: `https://<hub>/stores/portainer/templates.json`.
"""

from __future__ import annotations

from typing import Any

from .common import Files, GenerateContext, ImageInput, json_text, plain

Json = dict[str, Any]


def template(image: ImageInput) -> Json:
    rt = image.rt
    env = []
    for item in image.env_items():
        entry: Json = {"name": item["name"], "label": item["title"] or item["name"], "default": item["value"]}
        if item["description"]:
            entry["description"] = plain(item["description"])
        if item["options"]:
            entry["select"] = [
                {"text": option, "value": option, **({"default": True} if option == item["value"] else {})}
                for option in item["options"]
            ]
        env.append(entry)
    out: Json = {
        "type": 1,
        "title": image.title,
        "name": image.name,
        "description": plain(image.summary_oneline),
        "note": image.ctx["setup"].strip() or plain(image.summary_oneline),
        "categories": image.categories,
        "platform": "linux",
        "logo": image.logo,
        "image": image.image_ref,
        "restart_policy": "unless-stopped",
    }
    if rt["network"] and not rt["network"]["optional"]:
        out["network"] = rt["network"]["mode"]
    ports = [
        f"{p['external']}:{p['internal']}" + ("" if "/" in p["internal"] else "/tcp")
        for p in rt["ports"]
        if not p["optional"]
    ]
    if ports:
        out["ports"] = ports
    volumes = [
        {"container": v["path"], "bind": v["host_path"], **({"readonly": True} if v["mode"] == "ro" else {})}
        for v in rt["volumes"]
    ]
    if volumes:
        out["volumes"] = volumes
    if env:
        out["env"] = env
    if rt["privileged"] is True:
        out["privileged"] = True
    if rt["hostname"] and not rt["hostname"]["optional"]:
        out["hostname"] = rt["hostname"]["value"]
    return out


def generate(ctx: GenerateContext) -> Files:
    templates = [template(image) for image in ctx.enabled("portainer")]
    return {"templates.json": json_text({"version": "3", "templates": templates})}
