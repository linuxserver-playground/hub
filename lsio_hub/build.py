"""
Builds dist/ from data/ by requesting every route of the FastAPI app through its test client and writing
each response to a file: the API, the generated OpenAPI spec and the docs pages. Pydantic validates every
response on the way, so data that doesn't fit the models is never published.

Usage: [SITE_URL=https://linuxserver-playground.github.io] [BASE_PATH=/hub/] python -m lsio_hub.build
"""

import logging
import shutil
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from . import responses
from .app import create_app
from .config import DATA_DIR, DIST_DIR, PUBLIC_DIR, SiteConfig
from .fleet import Fleet, load_fleet
from .store import load_store

log = logging.getLogger(__name__)

Files = dict[str, bytes]


def route_values(route: APIRoute, fleet: Fleet) -> list[dict[str, str]]:
    """Every combination of path parameter values a route is built for; only files that exist are written."""
    params = list(route.param_convertors)
    path = route.path
    if not params:
        return [{}]
    if params == ["name"]:
        for kind in ("proxy", "kubernetes", "quadlet"):
            if path.endswith((f"/{kind}.json", f"/{kind}.yaml", f"/{kind}.container")):
                return [{"name": n} for n in responses.names_with(fleet, kind)]
        return [{"name": image.name} for image in fleet.images]
    if params == ["name", "tag"]:
        if path.endswith("/tests.json"):
            return [{"name": n, "tag": t} for n, t in responses.test_routes(fleet) if fleet.image(n)]
        if path.endswith("/vulns.json"):
            return [{"name": n, "tag": t} for n, t in responses.vuln_routes(fleet) if fleet.image(n)]
        return [
            {"name": name, "tag": tag}
            for name, record in sorted(fleet.store.images.items())
            for tag in sorted(record.builds)
            if fleet.image(name)
        ]
    if params == ["name", "tag", "arch"]:
        triples = responses.layer_routes(fleet) if "/layers." in path else responses.package_routes(fleet)
        return [{"name": n, "tag": t, "arch": a} for n, t, a in triples if fleet.image(n)]
    if params == ["package"]:
        return [{"package": slug} for slug in responses.package_slugs(fleet)]
    raise ValueError(f"{path}: no values to build {', '.join(params)} with")


def route_paths(app: FastAPI, fleet: Fleet) -> list[str]:
    """Every route's path, with each path parameter expanded to all its values."""
    paths = []
    for route in app.routes:
        if isinstance(route, APIRoute):
            paths += [route.path_format.format(**values) for values in route_values(route, fleet)]
    return paths


def render(fleet: Fleet, config: SiteConfig) -> Files:
    """Every generated file of the site, by path relative to the site root. Raises if any route fails."""
    app = create_app(fleet, config)
    files: Files = {}
    with TestClient(app) as client:
        for path in route_paths(app, fleet):
            res = client.get(path)
            res.raise_for_status()
            files[path.lstrip("/") or "index.html"] = res.content
        missing = client.get("/404.html")
        assert missing.status_code == 404, missing.status_code
        files["404.html"] = missing.content
    return files


def write_site(out_dir: Path, files: Files) -> None:
    shutil.rmtree(out_dir, ignore_errors=True)
    shutil.copytree(PUBLIC_DIR, out_dir)
    for path, content in files.items():
        target = out_dir / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("httpx2").setLevel(logging.WARNING)
    config = SiteConfig.from_env()
    fleet = load_fleet(load_store(DATA_DIR), config)
    if not fleet.images:
        log.error("No images in data/. Run `python -m lsio_hub.ingest --reconcile` first.")
        return 1
    files = render(fleet, config)
    write_site(DIST_DIR, files)
    log.info("Built %d files for %d images into dist/ (%s)", len(files), len(fleet.images), config.site_root)
    return 0


if __name__ == "__main__":
    sys.exit(main())
