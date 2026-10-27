"""
The mods index. Every branch of linuxserver-playground/docker-mods carries a mod.yml (schemas/mod.schema.json);
the hub reads them all into data/mods.json. A mod's `images` (the images it is curated for besides its target)
become `applies_to`, after the target.

Each mod's `builds` say what `ghcr.io/linuxserver-playground/mods` holds for it, one entry per version line (the
default line first; CONVENTIONS §3, "Mods"): the version and date of the newest build, the exact tag that pins it and
the floating tags that follow the line. The default line is read from the floating `:<branch>` tag itself. Another
line has no floating tag of its own, so its version is resolved with the build's resolver (workflows'
`scripts/resolve_version.py`, checked out by refresh.yml at RESOLVE_VERSION, never copied here) and read from
`:<branch>-<version>`; until that tag exists the line keeps what the previous refresh found.

    GITHUB_TOKEN=... [RESOLVE_VERSION=../workflows/scripts/resolve_version.py] python -m lsio_hub.mods
"""

from __future__ import annotations

import datetime
import importlib.util
import logging
import os
import re
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx2
import yaml
from builder.mods import line_tag_suffixes, upstream_lines, upstream_source_label
from contracts import ContractError, validate

from .config import DATA_DIR, MODS_IMAGE, MODS_REPO
from .sources.github import GitHub
from .sources.http import client
from .sources.registry import GhcrPackage
from .store import Store, load_store, save_store

log = logging.getLogger(__name__)
Json = dict[str, Any]

SKIP_BRANCHES = {"master", "main", "template"}
TAG_UNSAFE = re.compile(r"[~,%@+;:/ ]")
"""What the mod build strips from a version before it tags it (CONVENTIONS §3)."""
Resolver = Callable[[Json, list[str]], str]
"""(a line's version source, the mod's platforms) -> the upstream version, as the build resolves it."""


def _now() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def from_manifest(data: Json, branch: str) -> Json:
    """A mod.yml as the API serves it."""
    deprecated = data.get("deprecated", {})
    upstream = data.get("upstream") or {}
    version = upstream.get("version")
    return {
        "name": data["name"],
        "target": data["target"],
        "title": data.get("title") or data["name"],
        "summary": data["summary"],
        "branch": branch,
        "url": f"https://github.com/{MODS_REPO}/tree/{branch}",
        "image": f"{MODS_IMAGE}:{branch}",
        "maintainers": list(data.get("maintainers", [])),
        "platforms": list(data.get("platforms", ["amd64", "arm64"])),
        "bases": list(data.get("bases", [])),
        "env": [
            {
                "name": e["name"],
                "description": e["description"],
                "default": e.get("default"),
                "required": bool(e.get("required", False)),
            }
            for e in data.get("env", [])
        ],
        "deprecated": bool(deprecated.get("status", False)),
        "deprecation_message": deprecated.get("message"),
        "applies_to": [data["target"], *[i for i in dict.fromkeys(data.get("images", [])) if i != data["target"]]],
        "docs": data.get("docs"),
        "upstream": (
            {"url": upstream.get("url"), "type": version["type"], "source": upstream_source_label(version)}
            if version
            else None
        ),
        "source": "playground",
    }


def fetch_playground_mods(gh: GitHub) -> list[tuple[Json, Json]]:
    """Every branch's mod.yml: the index entry and the manifest it came from."""
    branches = gh.paginate(f"repos/{MODS_REPO}/branches")
    mods = []
    for branch in branches:
        name = branch["name"]
        if name in SKIP_BRANCHES:
            continue
        text = gh.file_text(MODS_REPO, "mod.yml", name)
        if text is None:
            log.info("  %s: no mod.yml", name)
            continue
        try:
            data = yaml.safe_load(text)
            validate("mod", data)
        except (yaml.YAMLError, ContractError) as e:
            log.warning("  ! %s: mod.yml invalid: %s", name, e)
            continue
        mods.append((from_manifest(data, name), data))
    return sorted(mods, key=lambda m: (m[0]["target"], m[0]["name"]))


def _build(branch: str, line: Json, image: Json, version: str | None, tag: str, tags: set[str]) -> Json:
    """One line's entry: what the newest build of the line is, the tag that pins it, the tags that follow it."""
    clean = TAG_UNSAFE.sub("", version) if version else None
    pin = None
    if clean and f"{branch}-{clean}" in tags:
        pin = f"{branch}-{clean}"
    elif image.get("revision") and f"{branch}-{image['revision'][:7]}" in tags:
        pin = f"{branch}-{image['revision'][:7]}"
    elif tag != branch:
        pin = tag
    floating = [branch] if line["name"] is None else []
    floating += (
        [f"{branch}-{s}" for s in line_tag_suffixes(clean, line["tags"]) if f"{branch}-{s}" in tags] if clean else []
    )
    return {
        "line": line["name"],
        "version": version,
        "built_at": image.get("created"),
        "pin": f"{MODS_IMAGE}:{pin}" if pin else None,
        "tags": [f"{MODS_IMAGE}:{t}" for t in floating],
        "digest": image.get("digest"),
        "revision": image.get("revision"),
    }


def _as_image(build: Json | None) -> Json | None:
    """A previous build entry in the shape GhcrPackage.image returns, so an unchanged digest costs one request."""
    if not build:
        return None
    return {
        "digest": build.get("digest"),
        "created": build.get("built_at"),
        "version": build.get("version"),
        "revision": build.get("revision"),
    }


def mod_builds(
    entry: Json, data: Json, package: GhcrPackage, tags: set[str], previous: list[Json], resolve: Resolver | None
) -> list[Json]:
    """What the mods package holds for one mod, per version line; [] when it was never published."""
    branch = entry["branch"]
    if branch not in tags:
        return []
    known = {b.get("line"): b for b in previous}
    lines = upstream_lines(data) or [{"name": None, "version": None, "tags": []}]
    image = package.image(branch, _as_image(known.get(None)))
    builds = [_build(branch, lines[0], image, image.get("version"), branch, tags)]
    for line in lines[1:]:
        kept = known.get(line["name"])
        version = None
        if resolve is not None:
            try:
                version = resolve(line["version"], entry["platforms"])
            except Exception as e:  # the resolver raises its own errors, and HTTP ones
                log.warning("  ! %s %s: version not resolved: %s", branch, line["name"], e)
        if version and version in {b["version"] for b in builds}:
            continue  # the earlier line builds a version two lines share (CONVENTIONS §3)
        tag = f"{branch}-{TAG_UNSAFE.sub('', version)}" if version else None
        if tag and tag in tags:
            builds.append(_build(branch, line, package.image(tag, _as_image(kept)), version, tag, tags))
        elif kept:
            builds.append(kept)
    return builds


def refresh_builds(
    mods: list[tuple[Json, Json]], previous: list[Json], package: GhcrPackage, resolve: Resolver | None
) -> str | None:
    """Set each entry's `builds`; registry errors keep the previous refresh's, and are returned for the status."""
    before = {m["branch"]: m.get("builds") or [] for m in previous}
    try:
        tags = set(package.tags())
    except httpx2.HTTPError as e:
        for entry, _ in mods:
            entry["builds"] = before.get(entry["branch"], [])
        return f"GHCR tags of the mods package: {e}"
    failed = []
    for entry, data in mods:
        try:
            entry["builds"] = mod_builds(entry, data, package, tags, before.get(entry["branch"], []), resolve)
        except httpx2.HTTPError as e:
            failed.append(f"{entry['branch']}: {e}")
            entry["builds"] = before.get(entry["branch"], [])
    return "builds kept from the previous run for " + "; ".join(failed) if failed else None


def load_resolver(path: str | Path | None) -> Resolver | None:
    """The build's resolver from a checkout of the workflows repository, or None when there is none."""
    if not path or not Path(path).is_file():
        return None
    spec = importlib.util.spec_from_file_location("resolve_version", path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    def resolve(source: Json, platforms: list[str]) -> str:
        return str(module.resolve({"upstream": {"version": source}, "build": {"platforms": platforms}})["upstream"])

    return resolve


def refresh_mods(
    store: Store,
    gh: GitHub,
    now: Callable[[], str] = _now,
    package: GhcrPackage | None = None,
    resolve: Resolver | None = None,
) -> None:
    checked_at = now()
    try:
        fetched = fetch_playground_mods(gh)
        source = f"mod.yml on each branch of {MODS_REPO}"
    except (httpx2.HTTPError, RuntimeError) as e:
        previous = store.status["sources"].get("mods", {})
        status: Json = {"ok": False, "checked_at": checked_at, "error": str(e)}
        if previous.get("fetched_at"):
            status["fetched_at"] = previous["fetched_at"]
        store.status["sources"]["mods"] = status
        log.warning("  x mods: %s (keeping previous data)", e)
        return
    previous_mods = store.mods.get("mods", [])
    error = None
    if package is not None:
        error = refresh_builds(fetched, previous_mods, package, resolve)
    else:
        before = {m["branch"]: m.get("builds") or [] for m in previous_mods}
        for entry, _ in fetched:
            entry["builds"] = before.get(entry["branch"], [])
    mods = [entry for entry, _ in fetched]
    store.mods = {"fetched_at": now(), "source": source, "mods": mods}
    store.status["sources"]["mods"] = {"ok": True, "checked_at": checked_at, "fetched_at": store.mods["fetched_at"]}
    if error:
        store.status["sources"]["mods"]["error"] = error
    log.info("  ok mods: %d from %s%s", len(mods), source, f" ({error})" if error else "")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("httpx2").setLevel(logging.WARNING)
    store = load_store(DATA_DIR)
    http = client()
    resolve = load_resolver(os.environ.get("RESOLVE_VERSION"))
    if resolve is None:
        log.info("  no RESOLVE_VERSION: version lines other than the default keep their previous builds")
    refresh_mods(
        store, GitHub(http, os.environ.get("GITHUB_TOKEN")), package=GhcrPackage(http, "mods"), resolve=resolve
    )
    log.info("%d files changed in data/", len(save_store(DATA_DIR, store)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
