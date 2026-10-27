"""
The PRoot Apps index. linuxserver-playground/proot-apps lists its apps in `metadata/metadata.yml` (name, full name,
category, arch, icon, description, `disabled`); the hub reads it into data/proot-apps.json for the site's PRoot
Apps page (/proot-apps/). Disabled apps are left out, as the repository's own README leaves them out. `cli` is the
newest release of the CLI, whose tarballs the install command downloads; null until the repository has one.

    GITHUB_TOKEN=... python -m lsio_hub.prootapps
"""

from __future__ import annotations

import datetime
import logging
import os
import sys
from collections.abc import Callable
from typing import Any

import httpx2
import yaml

from .config import DATA_DIR, PROOT_APPS_IMAGE, PROOT_APPS_REPO
from .sources.github import GitHub
from .sources.http import client
from .store import Store, load_store, save_store

log = logging.getLogger(__name__)
Json = dict[str, Any]

METADATA = "metadata/metadata.yml"


def _now() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def from_metadata(app: Json, ref: str) -> Json:
    """One metadata.yml entry as the API serves it."""
    name = str(app["name"])
    icon = app.get("icon")
    return {
        "name": name,
        "title": str(app.get("full_name") or name).strip(),
        "category": app.get("category") or "Other",
        "description": str(app.get("description") or "").strip(),
        "platforms": [p.strip().removeprefix("linux/") for p in str(app.get("arch") or "linux/amd64").split(",")],
        "icon": f"https://raw.githubusercontent.com/{PROOT_APPS_REPO}/{ref}/metadata/img/{icon}" if icon else None,
        "image": f"{PROOT_APPS_IMAGE}:{name}",
        "url": f"https://github.com/{PROOT_APPS_REPO}/tree/{ref}/apps/{name}",
    }


def latest_cli(gh: GitHub) -> Json | None:
    """The newest release that is not a prerelease: its tag, page and date."""
    for release in gh.releases(PROOT_APPS_REPO, max_pages=1):
        if not release.get("prerelease"):
            return {
                "version": release["tag_name"],
                "url": release["html_url"],
                "published_at": release.get("published_at") or release.get("created_at"),
            }
    return None


def refresh_proot_apps(store: Store, gh: GitHub, now: Callable[[], str] = _now) -> None:
    checked_at = now()
    try:
        ref = str(gh.get(f"repos/{PROOT_APPS_REPO}")["default_branch"])
        text = gh.file_text(PROOT_APPS_REPO, METADATA, ref)
        if text is None:
            raise RuntimeError(f"{METADATA} not found on {ref}")
        entries = (yaml.safe_load(text) or {}).get("include") or []
        cli = latest_cli(gh)
    except (httpx2.HTTPError, RuntimeError, yaml.YAMLError) as e:
        previous = store.status["sources"].get("proot-apps", {})
        status: Json = {"ok": False, "checked_at": checked_at, "error": str(e)}
        if previous.get("fetched_at"):
            status["fetched_at"] = previous["fetched_at"]
        store.status["sources"]["proot-apps"] = status
        log.warning("  x proot-apps: %s (keeping previous data)", e)
        return
    apps = sorted(
        (from_metadata(a, ref) for a in entries if a.get("name") and not a.get("disabled")),
        key=lambda a: a["title"].lower(),
    )
    source = f"{METADATA} of {PROOT_APPS_REPO}"
    store.proot_apps = {"fetched_at": now(), "source": source, "cli": cli, "apps": apps}
    store.status["sources"]["proot-apps"] = {"ok": True, "checked_at": checked_at, "fetched_at": checked_at}
    log.info("  ok proot-apps: %d apps from %s", len(apps), source)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("httpx2").setLevel(logging.WARNING)
    store = load_store(DATA_DIR)
    refresh_proot_apps(store, GitHub(client(), os.environ.get("GITHUB_TOKEN")))
    log.info("%d files changed in data/", len(save_store(DATA_DIR, store)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
