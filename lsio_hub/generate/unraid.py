"""
Unraid Community Applications templates, a port of the legacy `unraid.xml.j2` field for field. The icon
is the manifest's `docs.logo`; the WebUI comes from `test.web`; `publish.unraid.requirement` fills
<Requires> and `publish.unraid.webui` overrides the WebUI template.

Import: Unraid reads templates from a repository; deploy.yml pushes this output to the root of unraid-store.
Images with `publish.stores.unraid: false` are listed in `ignore.list`; deprecated images move to `deprecated/`.
"""

from __future__ import annotations

from html import escape
from typing import Any

from ..config import ORG, UNRAID_RAW_URL
from .common import Files, GenerateContext, ImageInput

Json = dict[str, Any]

DONATE_IMG = "https://raw.githubusercontent.com/linuxserver/docker-templates/master/linuxserver.io/img/donate.png"
SKIP_ENVS = {"puid", "pgid", "tz", "umask"}
"""Variables Unraid adds itself or that are hard coded below."""


def ca(text: str) -> str:
    """The legacy `ca` macro: no angle or square brackets, & as 'and', then XML-escaped."""
    cleaned = text.replace("<", "").replace(">", "").replace("[", "").replace("]", "").replace("&", "and")
    return escape(cleaned, quote=True)


def mask(name: str) -> str:
    return "true" if any(k in name.lower() for k in ("token", "pass", "key")) else "false"


def extra_params(image: ImageInput) -> list[str]:
    rt = image.rt
    params: list[str] = []
    if rt["hostname"] and not rt["hostname"]["optional"]:
        params.append(f"--hostname={rt['hostname']['value']}")
    if rt["mac_address"] and not rt["mac_address"]["optional"]:
        params.append(f"--mac-address={rt['mac_address']['value']}")
    for cap in rt["cap_add"]:
        if not cap["optional"]:
            params.append(f"--cap-add={cap['cap']}")
    for custom in rt["custom"]:
        if not custom["optional"]:
            params += [f"--{custom['flag']}={value}" for value in custom["values"]]
    for sec in rt["security_opt"]:
        if not sec["optional"]:
            params.append(f"--security-opt {sec['run']}")
    return params


def _config(name: str, attrs: list[tuple[str, str]]) -> str:
    rendered = " ".join(f'{key}="{value}"' for key, value in attrs)
    return f'    <Config Name="{name}" {rendered}/>'


def _port_configs(image: ImageInput) -> list[str]:
    lines = []
    for index, port in enumerate(image.rt["ports"]):
        number, _, proto = port["internal"].partition("/")
        if port["name"]:
            label = ca(port["name"])
        elif index == 0 and not port["optional"]:
            label = "WebUI"
        else:
            label = f"Port: {number}"
        lines.append(
            _config(
                label,
                [
                    ("Target", number),
                    ("Default", ca(port["external"])),
                    ("Mode", proto or "tcp"),
                    ("Description", ca(port["description"]) if port["description"] else f"Container Port: {number}"),
                    ("Type", "Port"),
                    ("Display", "always"),
                    ("Required", "false" if port["optional"] else "true"),
                    ("Mask", "false"),
                ],
            )
        )
    return lines


def _volume_configs(image: ImageInput) -> list[str]:
    lines = []
    for volume in image.rt["volumes"]:
        path = volume["path"]
        label = ca(volume["name"]) if volume["name"] else ("Appdata" if path == "/config" else f"Path: {path}")
        lines.append(
            _config(
                label,
                [
                    ("Target", ca(path)),
                    ("Default", ca(volume["host_path"]) if volume["default_host_path"] else ""),
                    ("Mode", volume["mode"]),
                    ("Description", ca(volume["description"]) if volume["description"] else f"Path: {path}"),
                    ("Type", "Path"),
                    ("Display", "advanced" if path == "/config" and not volume["optional"] else "always"),
                    ("Required", "false" if volume["optional"] else "true"),
                    ("Mask", "false"),
                ],
            )
        )
    return lines


def _env_configs(image: ImageInput) -> list[str]:
    lines = []
    for env in image.rt["env"]:
        if env["name"].lower() in SKIP_ENVS:
            continue
        default = "|".join(env["options"]) if env["options"] and not env["optional"] else ca(env["value"])
        lines.append(
            _config(
                ca(env["title"]) if env["title"] else env["name"],
                [
                    ("Target", env["name"]),
                    ("Default", default),
                    ("Description", ca(env["description"]) if env["description"] else f"Variable: {env['name']}"),
                    ("Type", "Variable"),
                    ("Display", "always"),
                    ("Required", "false" if env["optional"] else "true"),
                    ("Mask", mask(env["name"])),
                ],
            )
        )
    return lines


def _device_configs(image: ImageInput) -> list[str]:
    return [
        _config(
            ca(device["name"]) if device["name"] else device["path"],
            [
                ("Default", device["host_path"]),
                ("Description", ca(device["description"]) if device["description"] else f"Device: {device['path']}"),
                ("Type", "Device"),
                ("Display", "always"),
                ("Required", "false" if device["optional"] else "true"),
                ("Mask", "false"),
            ],
        )
        for device in image.rt["devices"]
    ]


def webui(image: ImageInput) -> str | None:
    override = image.manifest.get("publish", {}).get("unraid", {}).get("webui")
    if override:
        return str(override)
    web = image.manifest.get("test", {}).get("web")
    if not web or image.manifest.get("test", {}).get("enabled", True) is False:
        return None
    path = web.get("path", "/")
    return f"{web.get('scheme', 'http')}://[IP]:[PORT:{web['port']}]{'' if path == '/' else path}"


def _indent(text: str, spaces: int) -> str:
    pad = " " * spaces
    return "\n".join(pad + line if line else line for line in text.strip().splitlines()).strip()


def render(image: ImageInput) -> str:
    m, ctx, rt = image.manifest, image.ctx, image.rt
    repo_url = image.repo_url
    has_setup = bool(ctx["setup"] or ctx["has_notices"] or ctx["selkies"])
    network = rt["network"]["mode"] if rt["network"] and not rt["network"]["optional"] else "bridge"
    setup_anchor = "#application-setup" if has_setup else ""
    lines = [
        '<?xml version="1.0"?>',
        "<!-- DO NOT CHANGE THIS FILE MANUALLY, IT IS AUTOMATICALLY GENERATED -->",
        f"<!-- GENERATED FROM {repo_url}/blob/{ctx['release_branch']}/image.yml -->",
        '<Container version="2">',
        f"    <Name>{rt['container_name'].lower()}</Name>",
        f"    <Repository>{ctx['image']}</Repository>",
        f"    <Registry>https://github.com/orgs/{ORG}/packages/container/package/{image.name}</Registry>",
        "    <DonateText>Donations</DonateText>",
        "    <DonateLink>https://www.linuxserver.io/donate</DonateLink>",
        f"    <DonateImg>{DONATE_IMG}</DonateImg>",
        f"    <Network>{network}</Network>",
        f"    <Privileged>{'true' if rt['privileged'] is True else 'false'}</Privileged>",
        f"    <Support>{repo_url}/issues/new/choose</Support>",
        "    <Shell>bash</Shell>",
    ]
    if image.deprecated:
        lines.append("    <Deprecated>true</Deprecated>")
    lines += [f"    <GitHub>{repo_url}{setup_anchor}</GitHub>", f"    <ReadMe>{repo_url}#readme</ReadMe>"]
    for tag in ctx["tags"]:
        if tag["deprecated"] or "deprecate" in tag["description"].lower():
            continue
        lines += [
            "    <Branch>",
            f"        <Tag>{ca(tag['tag'])}</Tag>",
            f"        <TagDescription>{ca(tag['description'])}</TagDescription>",
        ]
        if tag["tag"] != "latest":
            lines.append(f"        <ReadMe>{repo_url}/tree/{tag['tag']}#readme</ReadMe>")
            lines.append(f"        <GitHub>{repo_url}/tree/{tag['tag']}{setup_anchor}</GitHub>")
        if tag["unraid_extra"]:
            lines.append(f"        {_indent(tag['unraid_extra'], 8)}")
        lines.append("    </Branch>")
    lines += [f"    <Project>{image.project_url}</Project>", f"    <Overview>{ca(image.summary_oneline)}</Overview>"]
    params = extra_params(image)
    if params:
        lines.append(f"    <ExtraParams>{escape(' '.join(params))}</ExtraParams>")
    web = webui(image)
    if web:
        lines.append(f"    <WebUI>{web}</WebUI>")
    lines.append(f"    <TemplateURL>{UNRAID_RAW_URL}/{image.name.lower()}.xml</TemplateURL>")
    lines.append(f"    <Icon>{image.logo}</Icon>")
    if image.screenshot:
        lines.append(f"    <Screenshot>{image.screenshot}</Screenshot>")
    requirement = m.get("publish", {}).get("unraid", {}).get("requirement", "")
    external = ctx["external_application"] or {}
    if requirement or external or ctx["selkies"]:
        lines.append("    <Requires>")
        if requirement:
            lines.append(f"        {_indent(ca(requirement), 4)}")
        if external:
            lines.append("        This container requires an external application to be run separately.")
            if external.get("unraid"):
                lines.append(f"        {_indent(ca(external['unraid']), 4)}")
        if ctx["selkies"]:
            lines.append("        This image is unprotected by default __**do not**__ expose it to the internet.")
            lines.append(f"        Please read {repo_url}#security for more information.")
        lines.append("    </Requires>")
    changelog = ctx["changelog"]
    if changelog:
        lines += [f"    <Date>{changelog[0]['date']}</Date>", "    <Changes>"]
        for entry in changelog:
            lines += [f"### {entry['date']}", f"- {ca(entry['text'])}", ""]
        lines.append("    </Changes>")
    lines += _port_configs(image)
    lines += _volume_configs(image)
    lines += _env_configs(image)
    lines += [
        _config(
            "PUID",
            [
                ("Target", "PUID"),
                ("Default", "99"),
                ("Description", "Container Variable: PUID"),
                ("Type", "Variable"),
                ("Display", "advanced"),
                ("Required", "true"),
                ("Mask", "false"),
            ],
        ),
        _config(
            "PGID",
            [
                ("Target", "PGID"),
                ("Default", "100"),
                ("Description", "Container Variable: PGID"),
                ("Type", "Variable"),
                ("Display", "advanced"),
                ("Required", "true"),
                ("Mask", "false"),
            ],
        ),
        _config(
            "UMASK",
            [
                ("Target", "UMASK"),
                ("Default", "022"),
                ("Description", "Container Variable: UMASK"),
                ("Type", "Variable"),
                ("Display", "advanced"),
                ("Required", "false"),
                ("Mask", "false"),
            ],
        ),
    ]
    lines += _device_configs(image)
    lines.append("</Container>")
    return "\n".join(lines) + "\n"


def generate(ctx: GenerateContext) -> Files:
    files: Files = {}
    ignored: list[str] = []
    for image in ctx.images:
        publish = image.manifest.get("publish", {}).get("stores", {}).get("unraid", True)
        if not publish:
            ignored.append(image.name)
            continue
        folder = "deprecated/" if image.deprecated else ""
        files[f"{folder}{image.name}.xml"] = render(image)
    files["ignore.list"] = "".join(f"{name}\n" for name in ignored)
    return files
