"""
Turns one image's record (manifests, builds, observed data) into an API image. The v1 fields keep the
meaning the original API gave them, now derived from the typed manifest and the build records instead of
readme-vars.yml and GitHub's latest release; the README lists every divergence.
"""

from __future__ import annotations

import logging
from typing import Any

from builder.manifest import Settings, build_context
from builder.snippets import compose, docker_run

from .config import SiteConfig
from .dates import python_timestamp
from .models import (
    Architecture,
    Cap,
    Changelog,
    Config,
    Custom,
    Device,
    EnvVar,
    Hostname,
    ImageDetail,
    ImageLinks,
    MacAddress,
    Port,
    Registries,
    ReleaseInfo,
    SecurityOpt,
    Snippets,
    Tag,
    Volume,
)
from .store import ImageRecord

log = logging.getLogger(__name__)
Json = dict[str, Any]

ARCHITECTURES = {"amd64": ("x86_64", "amd64-latest"), "arm64": ("arm64", "arm64v8-latest")}
"""v1 `architectures` entries per manifest platform."""

COMMON_ENV = [("PUID", "1000", "User ID"), ("PGID", "1000", "Group ID"), ("TZ", "Etc/UTC", "Timezone")]
"""The common variables as the original API described them."""

EPOCH = "1970-01-01T00:00:00Z"


def _scalar[T](item: Json | None, make: Any) -> T | None:
    return make(item) if item else None


def get_config(ctx: Json, manifest: Json, github_url: str) -> Config:
    rt = ctx["rt"]
    runtime = manifest.get("runtime", {})
    env_vars: list[EnvVar] = []
    if rt["common_env"]:
        env_vars = [EnvVar(name=n, value=v, desc=d, optional=rt["common_env"] == "optional") for n, v, d in COMMON_ENV]
    env_vars += [
        EnvVar(name=e["name"], value=e["value"], desc=e["description"], optional=e["optional"]) for e in rt["env"]
    ]
    setup = bool(ctx["setup"] or ctx["has_notices"] or ctx["selkies"])
    return Config(
        application_setup=f"{github_url}?tab=readme-ov-file#application-setup" if setup else None,
        readonly_supported=rt["readonly"]["supported"] if "readonly" in runtime else None,
        nonroot_supported=rt["nonroot"]["supported"] if "nonroot" in runtime else None,
        privileged=True if rt["privileged"] else None,
        networking=rt["network"]["mode"] if rt["network"] else None,
        hostname=_scalar(
            rt["hostname"],
            lambda h: Hostname(hostname=h["value"], desc=h["description"], optional=h["optional"]),
        ),
        mac_address=_scalar(
            rt["mac_address"],
            lambda m: MacAddress(mac_address=m["value"], desc=m["description"], optional=m["optional"]),
        ),
        env_vars=env_vars or None,
        volumes=[
            Volume(path=v["path"], host_path=v["host_path"], desc=v["description"], optional=v["optional"])
            for v in rt["volumes"]
        ]
        or None,
        ports=[
            Port(external=p["external"], internal=p["internal"], desc=p["description"], optional=p["optional"])
            for p in rt["ports"]
        ]
        or None,
        custom=[
            Custom(
                name=c["flag"],
                name_compose=c["compose"],
                value=c["values"] if c["is_array"] else c["values"][0],
                desc=c["description"],
                optional=c["optional"],
            )
            for c in rt["custom"]
        ]
        or None,
        security_opt=[
            SecurityOpt(run_var=s["run"], compose_var=s["compose"], desc=s["description"], optional=s["optional"])
            for s in rt["security_opt"]
        ]
        or None,
        devices=[
            Device(path=d["path"], host_path=d["host_path"], desc=d["description"], optional=d["optional"])
            for d in rt["devices"]
        ]
        or None,
        caps=[Cap(cap_add=c["cap"], desc=c["description"], optional=c["optional"]) for c in rt["cap_add"]] or None,
    )


def get_tags(ctx: Json) -> tuple[list[Tag], bool]:
    if not ctx["tags"]:
        return [Tag(tag="latest", desc="Stable releases")], True
    return [Tag(tag=t["tag"], desc=t["description"]) for t in ctx["tags"]], bool(ctx["has_latest"])


def get_changelog(manifest: Json) -> tuple[list[Changelog] | None, str | None]:
    entries = [Changelog(date=str(c["date"]), desc=c["text"]) for c in manifest.get("changelog", [])]
    if not entries:
        return None, None
    return entries, min(entries, key=lambda c: c.date).date


def _release_info(record: ImageRecord, branch: str, manifest: Json) -> ReleaseInfo:
    build = record.latest_build(branch)
    pointer = record.latest.get(branch, {})
    return ReleaseInfo(
        branch=branch,
        release_tag=manifest["release"]["tag"],
        channel=manifest["release"].get("channel", "stable"),
        tag=build["version"]["tag"] if build else None,
        upstream_version=build["version"]["upstream"] if build else None,
        created=build["created"] if build else None,
        release_url=pointer.get("release_url"),
        test_success=build["test"]["success"] if build and build["test"].get("enabled", True) else None,
        base=build["base"]["image"] if build else None,
        platforms=[p["arch"] for p in build["platforms"] if p["result"] == "success"] if build else [],
    )


def build_image(
    record: ImageRecord, observed: Json, settings: Settings, site: SiteConfig, fallback_time: str | None
) -> ImageDetail | None:
    """The API image for a record, or None when it has no manifest yet."""
    manifest = record.manifest
    if manifest is None:
        return None
    ctx = build_context(manifest, settings)
    name = record.name
    github_url = ctx["repo_url"]
    tags, stable = get_tags(ctx)
    changelog, initial_date = get_changelog(manifest)
    build = record.latest_build()
    pointer = record.latest.get(record.default_branch or "", {})
    config = get_config(ctx, manifest, github_url)
    deprecated = bool(ctx["deprecation"]["status"])
    publish = manifest.get("publish", {})
    kubernetes = publish.get("kubernetes", {}).get("enabled", True)
    quadlet = publish.get("quadlet", True)
    api = f"{site.api_root}/api/v1/catalog/{name}"
    timestamp = build["created"] if build else (observed.get("pushed_at") or fallback_time or EPOCH)
    return ImageDetail(
        name=name,
        initial_date=initial_date,
        github_url=github_url,
        project_url=manifest["upstream"].get("url"),
        project_logo=ctx["logo"] or None,
        description=ctx["summary"].replace("\n", " ").strip(),
        version=build["version"]["tag"] if build else "latest",
        version_timestamp=python_timestamp(timestamp),
        category=",".join(manifest["docs"]["categories"]),
        stable=stable,
        deprecated=deprecated,
        stars=int(observed.get("stars", 0)),
        monthly_pulls=None,
        tags=tags,
        architectures=[Architecture(arch=ARCHITECTURES[a][0], tag=ARCHITECTURES[a][1]) for a in ctx["platforms"]],
        changelog=changelog,
        config=config,
        title=ctx["title"],
        categories=list(dict.fromkeys(manifest["docs"]["categories"])),
        deprecation_message=ctx["deprecation"]["message"] or None if deprecated else None,
        setup_instructions=ctx["setup"].strip() or None,
        archived=bool(observed.get("archived", False)),
        release_url=pointer.get("release_url"),
        upstream_version=build["version"]["upstream"] if build else None,
        base=ctx["base"],
        releases=[_release_info(record, branch, m) for branch, m in sorted(record.manifests.items())],
        docs_url=f"{settings.docs_url}/images/{ctx['repo']}/",
        registries=Registries(
            ghcr=ctx["image"], packages_url=f"https://github.com/orgs/{settings.org}/packages/container/package/{name}"
        ),
        snippets=Snippets(docker_compose=compose(ctx), docker_run=docker_run(ctx)),
        links=ImageLinks(
            builds=f"{api}/builds.json",
            docs=f"{site.api_root}/stores/docs/images/{ctx['repo']}.md",
            proxy=f"{api}/proxy.json" if manifest.get("proxy") else None,
            kubernetes=f"{api}/kubernetes.yaml" if kubernetes else None,
            quadlet=f"{api}/quadlet.container" if quadlet else None,
            mods=f"{api}/mods.json",
        ),
    )


def build_images(
    records: dict[str, ImageRecord], observed: Json, settings: Settings, site: SiteConfig, fallback_time: str | None
) -> list[ImageDetail]:
    """Every image with a manifest, sorted by name. One broken record costs only that image."""
    images = []
    for name in sorted(records):
        try:
            image = build_image(records[name], observed.get("images", {}).get(name, {}), settings, site, fallback_time)
        except Exception as e:
            log.warning("  ! skipped %s: %s", name, e)
            continue
        if image is not None:
            images.append(image)
    return images
