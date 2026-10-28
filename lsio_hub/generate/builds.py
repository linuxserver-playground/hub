"""
CI result pages: one plain page per held build with the result per architecture, the test table from
test.<arch>.json, the runtime probe, the diff summary and links, and a build history page per image, at
`https://<hub>/builds/<image>/<tag>/`. The website's build page is the report people read; these stay because
older release notes and bundles (`test.report_url`) and CONVENTIONS §10 still link them.

Nothing heavy is copied here any more. The screenshot, the logs and the file trees are on the image repository's
own Pages (`config.repo_pages`), which keeps the same newest builds the hub does, and the pages link there; the
tarballs stay on the Release as downloads. So this generator reads data/ only and downloads nothing.
"""

from __future__ import annotations

from typing import Any

from ..config import REPORT_FILES, build_pages
from ..templating import TEMPLATES, env
from .common import Files, GenerateContext, ImageInput

Json = dict[str, Any]

EXTRA_FILES = ("package_diff.txt",)
"""Files the harness may add to the report beyond those `files` names; linked, and absent when it wrote none."""


def _asset_url(build: Json, name: str) -> str | None:
    return next((str(a["url"]) for a in build.get("assets", []) if a["name"] == name and a.get("url")), None)


def _pill(value: Any) -> str:
    return str(value).lower() if isinstance(value, bool) else str(value)


def _build_view(image: ImageInput, build: Json, ctx: GenerateContext) -> Json:
    tag = build["version"]["tag"]
    diff = image.record.diffs.get(tag)
    tests = image.record.tests.get(tag, {})
    api = f"{ctx.site.api_root}/api/v1/catalog/{image.name}/builds/{tag}"
    pages = build_pages(build["repository"], tag)
    names = {a["name"] for a in build.get("assets", [])}
    release_url = next(
        (h.get("release_url") for h in image.record.history.get(build["branch"], []) if h["tag"] == tag), None
    )
    arches = []
    for platform in build["platforms"]:
        arch = platform["arch"]
        report = tests.get(arch)
        kinds = (report or {}).get("files") or {}
        files = [REPORT_FILES[k] for k in REPORT_FILES if k in kinds] + list(EXTRA_FILES if report else ())
        arches.append(
            {
                "arch": arch,
                "platform": platform,
                "report": report,
                "tests": (report or {}).get("tests", []),
                "runtime": (report or {}).get("runtime", {}),
                "warnings": (report or {}).get("warnings", {}),
                "tarball": _asset_url(build, f"test.{arch}.tar.gz"),
                "report_files": [(name, f"{pages}{arch}/{name}") for name in files],
                "screenshot": f"{pages}{arch}/{REPORT_FILES['screenshot']}" if "screenshot" in kinds else None,
                "files": f"{pages}files.{arch}.json.gz" if f"files.{arch}.json.gz" in names else None,
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
    }


def generate(ctx: GenerateContext) -> Files:
    files: Files = {"report.css": (TEMPLATES / "report.css").read_text(encoding="utf-8")}
    build_template = env.get_template("report_build.html")
    history_template = env.get_template("report_history.html")
    for image in ctx.images:
        views = [_build_view(image, build, ctx) for build in image.record.sorted_builds()]
        files[f"{image.name}/index.html"] = history_template.render(image=image, views=views, site=ctx.site, pill=_pill)
        for view in views:
            page = build_template.render(view=view, site=ctx.site, pill=_pill)
            files[f"{image.name}/{view['tag']}/index.html"] = page
    return files
