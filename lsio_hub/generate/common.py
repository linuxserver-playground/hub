"""What every generator starts from: the images with their manifest context, the store and the site config."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import yaml
from builder.manifest import Settings, build_context

from ..config import SiteConfig
from ..store import ImageRecord, Store

Json = dict[str, Any]
Files = dict[str, str | bytes]
"""Generated files by path relative to the generator's output directory."""
Fetch = Callable[[str], bytes | None]
"""Downloads a URL, or returns None when it cannot (offline, missing asset)."""


def no_fetch(url: str) -> bytes | None:
    return None


@dataclass
class ImageInput:
    name: str
    record: ImageRecord
    manifest: Json
    """The default branch's manifest."""
    ctx: Json
    """builder's render context for that manifest: normalised runtime, titles, URLs."""
    observed: Json
    screenshot: str | None = None
    """The ci screenshot of the newest default-branch build, from its hub build report, when one passed."""

    @property
    def rt(self) -> Json:
        rt: Json = self.ctx["rt"]
        return rt

    @property
    def title(self) -> str:
        return str(self.ctx["title"])

    @property
    def deprecated(self) -> bool:
        return bool(self.ctx["deprecation"]["status"])

    @property
    def latest_build(self) -> Json | None:
        return self.record.latest_build()

    @property
    def version(self) -> str:
        """The upstream version of the newest build on the default branch, or `latest` before the first build."""
        build = self.latest_build
        return str(build["version"]["upstream_clean"]) if build else "latest"

    @property
    def build_date(self) -> str | None:
        build = self.latest_build
        return str(build["created"])[:10] if build else None

    @property
    def platforms(self) -> list[str]:
        return list(self.ctx["platforms"])

    @property
    def image_ref(self) -> str:
        return str(self.ctx["image_ref"])

    @property
    def logo(self) -> str:
        return str(self.ctx["logo"])

    @property
    def summary_oneline(self) -> str:
        return str(self.ctx["summary_oneline"])

    @property
    def project_url(self) -> str:
        return str(self.ctx["project_url"])

    @property
    def repo_url(self) -> str:
        return str(self.ctx["repo_url"])

    @property
    def kind(self) -> str:
        return str(self.manifest.get("kind", "app"))

    @property
    def categories(self) -> list[str]:
        return list(self.manifest["docs"]["categories"])

    def store_enabled(self, platform: str) -> bool:
        """`publish.stores.<platform>`, default true; deprecated images, base images and tools are left out of every
        store."""
        if self.deprecated or self.kind != "app":
            return False
        return bool(self.manifest.get("publish", {}).get("stores", {}).get(platform, True))

    @property
    def web_port(self) -> str | None:
        """The port a store opens: the first required port, else the test web port."""
        required = [p for p in self.rt["ports"] if not p["optional"]]
        if required:
            return str(required[0]["external"])
        web = self.manifest.get("test", {}).get("web")
        return str(web["port"]) if web else None

    @property
    def web_scheme(self) -> str:
        web = self.manifest.get("test", {}).get("web") or {}
        return str(web.get("scheme", "http"))

    @property
    def web_path(self) -> str:
        web = self.manifest.get("test", {}).get("web") or {}
        return str(web.get("path", "/"))

    def env_items(self, *, optional: bool = True) -> list[Json]:
        """Common variables then the image's own, as a store presents them."""
        items = []
        if self.rt["common_env"]:
            items += [dict(e, optional=False, options=[], title="", secret=False) for e in self.rt["common_env_vars"]]
        items += [e for e in self.rt["env"] if optional or not e["optional"]]
        return items


@dataclass
class GenerateContext:
    store: Store
    images: list[ImageInput]
    site: SiteConfig
    settings: Settings
    fetch: Fetch = no_fetch
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def current(self) -> list[ImageInput]:
        return [i for i in self.images if not i.deprecated]

    @property
    def apps(self) -> list[ImageInput]:
        """Current applications: what install artefacts (kubernetes, quadlets, proxy confs) are generated for."""
        return [i for i in self.current if i.kind == "app"]

    def enabled(self, platform: str) -> list[ImageInput]:
        return [i for i in self.images if i.store_enabled(platform)]


def image_inputs(store: Store, settings: Settings) -> list[ImageInput]:
    inputs = []
    for name in sorted(store.images):
        record = store.images[name]
        manifest = record.manifest
        if manifest is None:
            continue
        observed = store.observed.get("images", {}).get(name, {})
        inputs.append(ImageInput(name, record, manifest, build_context(manifest, settings), observed))
    return inputs


def screenshot_url(record: ImageRecord, site: SiteConfig) -> str | None:
    """Where the build reports serve the newest default-branch build's screenshot, amd64 first. Only a passing
    "Take screenshot" test counts, so a store never shows a timeout or an error page."""
    build = record.latest_build()
    if not build:
        return None
    tag = build["version"]["tag"]
    reports = record.tests.get(tag, {})
    for arch in ("amd64", "arm64"):
        report = reports.get(arch) or {}
        shot = next((t for t in report.get("tests") or [] if t.get("name") == "Take screenshot"), None)
        if shot and str(shot.get("status", "")).upper() == "PASS" and (report.get("files") or {}).get("screenshot"):
            return f"{site.api_root}/builds/{record.name}/{tag}/{arch}/screenshot.png"
    return None


def make_context(store: Store, site: SiteConfig, settings: Settings, fetch: Fetch = no_fetch) -> GenerateContext:
    images = image_inputs(store, settings)
    for image in images:
        image.screenshot = screenshot_url(image.record, site)
    return GenerateContext(store=store, images=images, site=site, settings=settings, fetch=fetch)


class _Dumper(yaml.SafeDumper):
    def ignore_aliases(self, data: Any) -> bool:
        return True


def _str_presenter(dumper: yaml.SafeDumper, data: str) -> yaml.Node:
    style = "|" if "\n" in data else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style=style)


_Dumper.add_representer(str, _str_presenter)


def yaml_text(value: Any, *, header: str | None = None) -> str:
    text = yaml.dump(value, Dumper=_Dumper, sort_keys=False, allow_unicode=True, width=1000, default_flow_style=False)
    return (f"{header}\n" if header else "") + text


def json_text(value: Any, *, indent: int | None = 2) -> str:
    return json.dumps(value, indent=indent, ensure_ascii=False) + "\n"


def category_slug(category: str) -> str:
    return "-".join("".join(c if c.isalnum() else " " for c in category.lower()).split())


def plain(text: str) -> str:
    """Markdown summary to plain text: links become their label, code marks and emphasis go."""
    import re

    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"[`*_]", "", text)
    return " ".join(text.split())
