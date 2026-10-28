"""
Redirects from the retired CI report pages to the website. The hub used to render a plain report page per build at
`https://<hub>/builds/<image>/<tag>/`; older release notes, bundles (`test.report_url`) and Discord posts link them.
The build's page on the website is the report now (CONVENTIONS §10), and the site renders any build the hub serves
or once served (its 404 page renders a build it predates, or one rotated out of data/, from the hub's API), so every
build the hub knows, held or only in history.json, gets a small page that sends the browser there, and each image's
`/builds/<image>/` goes to the build list on its page.
"""

from __future__ import annotations

import re
from html import escape

from ..config import site_build, site_builds
from .common import Files, GenerateContext

TAG = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
"""A release tag that is safe as one path segment (every tag the build workflow makes)."""


def redirect(target: str, title: str) -> str:
    """A page of a few hundred bytes that moves the browser to `target`: a meta refresh, the canonical link and a
    plain link for anything that does not follow either."""
    url = escape(target, quote=True)
    return (
        f'<!doctype html><html lang="en"><meta charset="utf-8"><title>{escape(title)}</title>'
        f'<meta name="robots" content="noindex"><link rel="canonical" href="{url}">'
        f'<meta http-equiv="refresh" content="0; url={url}">'
        f'<p>Moved to <a href="{url}">{escape(title)} on the website</a>.</p></html>\n'
    )


def generate(ctx: GenerateContext) -> Files:
    files: Files = {}
    for image in ctx.images:
        record = image.record
        tags = set(record.builds) | {str(h.get("tag")) for entries in record.history.values() for h in entries}
        tags = {t for t in tags if TAG.fullmatch(t)}
        if not tags:
            continue
        files[f"{image.name}/index.html"] = redirect(site_builds(image.name), f"{image.name} builds")
        for tag in sorted(tags):
            files[f"{image.name}/{tag}/index.html"] = redirect(site_build(image.name, tag), f"{image.name} {tag}")
    return files
