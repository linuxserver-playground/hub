"""
CI result pages: one page per ingested live build with the result per architecture, the test table from
test.<arch>.json, the runtime probe, the diff summary and links, plus the unpacked `test.<arch>.tar.gz`
(HTML report, screenshot, logs) next to it; and a build history page per image. These are the deterministic
report URLs other systems link to: `https://<hub>/builds/<image>/<tag>/`.

Tarballs and `files.<arch>.json.gz` are never kept in git: they are downloaded from the Release when the
pages are generated (`ctx.fetch`), the tarballs for every retained build, the file trees for the newest build
of each branch only. Older builds link to the Release asset instead. A build's unpacked report is
downloaded once: an `<arch>/` directory already in the output (`ctx.extra["existing"]`) is kept as it is,
so a cached out/builds/ makes a run cheap, and a rotated build's directory is removed.
"""

from __future__ import annotations

import io
import json
import posixpath
import tarfile
from typing import Any

from ..config import ARCHES
from ..templating import TEMPLATES, env
from .common import Files, GenerateContext, ImageInput

Json = dict[str, Any]

MAX_TARBALL_BYTES = 64 * 1024 * 1024
"""Extracted bytes allowed per tarball; anything beyond is left on the Release."""

REPORT_FILES = {
    "html": "index.html",
    "screenshot": "screenshot.png",
    "container_log": "container.log",
    "browser_log": "browser.log",
    "sysinfo": "sysinfo.txt",
    "shellcheck": "shellcheck.xml",
}
"""test.<arch>.json `files` keys and the fixed names they get under <arch>/."""
EXTRA_FILES = ("package_diff.txt",)
"""Files copied by name when the tarball has them."""
FETCHED = "fetched.json"
"""Written under <arch>/ once the tarball is unpacked: the names it held, possibly none."""


def _asset_url(image: ImageInput, build: Json, name: str) -> str | None:
    for asset in build.get("assets", []):
        if asset["name"] == name and asset.get("url"):
            return str(asset["url"])
    pointer = image.record.latest.get(build["branch"], {})
    if pointer.get("tag") == build["version"]["tag"]:
        url = pointer.get("assets", {}).get(name)
        return str(url) if url else None
    return None


def _member_path(member: tarfile.TarInfo) -> str | None:
    """The normalised relative path of a regular file, or None for anything that escapes the archive root."""
    if not member.isreg():
        return None
    path = posixpath.normpath(member.name)
    if path.startswith(("/", "../")) or path in (".", ".."):
        return None
    return path


def unpack(data: bytes, report: Json | None) -> dict[str, bytes]:
    """
    The tarball's regular files as {name under <arch>/: bytes}: the report's named files under their fixed
    names, the extra files by basename, everything else under its path in the archive (one leading
    directory stripped). Stops at MAX_TARBALL_BYTES.
    """
    out: dict[str, bytes] = {}
    named = {v: REPORT_FILES[k] for k, v in (report or {}).get("files", {}).items() if k in REPORT_FILES}
    total = 0
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        members = [(m, p) for m in tar.getmembers() if (p := _member_path(m)) is not None]
        roots = {p.split("/", 1)[0] for _, p in members if "/" in p}
        strip = next(iter(roots)) + "/" if len(roots) == 1 and all("/" in p for _, p in members) else ""
        for member, path in members:
            if total + member.size > MAX_TARBALL_BYTES:
                break
            handle = tar.extractfile(member)
            if handle is None:
                continue
            content = handle.read()
            total += len(content)
            short = path[len(strip) :] if strip and path.startswith(strip) else path
            base = posixpath.basename(short)
            target = named.get(path) or named.get(short) or (base if base in EXTRA_FILES else short)
            out[target] = content
    return out


def _pill(value: Any) -> str:
    return str(value).lower() if isinstance(value, bool) else str(value)


def _build_view(image: ImageInput, build: Json, ctx: GenerateContext) -> Json:
    tag = build["version"]["tag"]
    diff = image.record.diffs.get(tag)
    tests = image.record.tests.get(tag, {})
    api = f"{ctx.site.api_root}/api/v1/catalog/{image.name}/builds/{tag}"
    release_url = next(
        (h.get("release_url") for h in image.record.history.get(build["branch"], []) if h["tag"] == tag), None
    )
    arches = []
    for platform in build["platforms"]:
        arch = platform["arch"]
        report = tests.get(arch)
        arches.append(
            {
                "arch": arch,
                "platform": platform,
                "report": report,
                "tests": (report or {}).get("tests", []),
                "runtime": (report or {}).get("runtime", {}),
                "warnings": (report or {}).get("warnings", {}),
                "tarball": _asset_url(image, build, f"test.{arch}.tar.gz"),
                "files_asset": _asset_url(image, build, f"files.{arch}.json.gz"),
            }
        )
    return {
        "image": image,
        "build": build,
        "tag": tag,
        "diff": diff,
        "arches": arches,
        "release_url": release_url,
        "api_build": f"{api}.json",
        "api_diff": f"{api}/diff.json",
        "is_latest": image.record.latest.get(build["branch"], {}).get("tag") == tag,
    }


def generate(ctx: GenerateContext) -> Files:
    """
    The pages, plus the report files and file trees not yet in the output directory. The ones already there
    that a retained build still uses are added to `ctx.extra["keep"]`; anything else there (rotated builds) goes.
    """
    existing: set[str] = set(ctx.extra.get("existing", set()))
    keep: set[str] = ctx.extra.setdefault("keep", set())
    files: Files = {"report.css": (TEMPLATES / "report.css").read_text(encoding="utf-8")}
    build_template = env.get_template("report_build.html")
    history_template = env.get_template("report_history.html")
    for image in ctx.images:
        builds = image.record.sorted_builds()
        views = [_build_view(image, build, ctx) for build in builds]
        files[f"{image.name}/index.html"] = history_template.render(image=image, views=views, site=ctx.site, pill=_pill)
        for view in views:
            tag = view["tag"]
            folder = f"{image.name}/{tag}"
            for arch_view in view["arches"]:
                arch = arch_view["arch"]
                prefix = f"{folder}/{arch}/"
                have = sorted(p for p in existing if p.startswith(prefix))
                if have:
                    keep.update(have)
                    names = [p[len(prefix) :] for p in have if p != prefix + FETCHED]
                elif arch_view["tarball"] and (data := ctx.fetch(arch_view["tarball"])):
                    try:
                        unpacked = unpack(data, arch_view["report"])
                    except (tarfile.TarError, OSError):
                        unpacked = {}
                    for name, content in unpacked.items():
                        files[prefix + name] = content
                    # Marks the tarball as fetched even when it held no report, so it is not downloaded again.
                    files[prefix + FETCHED] = json.dumps(sorted(unpacked)) + "\n"
                    names = sorted(unpacked)
                else:
                    names = []
                arch_view["unpacked"] = names
                arch_view["has_report"] = "index.html" in names
                arch_view["has_screenshot"] = "screenshot.png" in names
                if view["is_latest"] and arch_view["files_asset"] and arch in ARCHES:
                    target = f"{folder}/files.{arch}.json.gz"
                    if target in existing:
                        keep.add(target)
                    elif tree := ctx.fetch(arch_view["files_asset"]):
                        files[target] = tree
                    arch_view["files_local"] = target in existing or target in files
            files[f"{folder}/index.html"] = build_template.render(view=view, site=ctx.site, pill=_pill)
    return files
