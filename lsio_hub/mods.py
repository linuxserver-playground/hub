"""
The mods index. Every branch of linuxserver-playground/docker-mods carries a mod.yml (schemas/mod.schema.json);
the hub reads them all into data/mods.json. A mod's `images` (the images it is curated for besides its target)
become `applies_to`, after the target.

    GITHUB_TOKEN=... python -m lsio_hub.mods
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
from contracts import ContractError, validate

from .config import DATA_DIR, MODS_IMAGE, MODS_REPO
from .sources.github import GitHub
from .sources.http import client
from .store import Store, load_store, save_store

log = logging.getLogger(__name__)
Json = dict[str, Any]

SKIP_BRANCHES = {"master", "main", "template"}


def _now() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def from_manifest(data: Json, branch: str) -> Json:
    """A mod.yml as the API serves it."""
    deprecated = data.get("deprecated", {})
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
        "source": "playground",
    }


def fetch_playground_mods(gh: GitHub) -> list[Json]:
    """Every branch's mod.yml."""
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
        mods.append(from_manifest(data, name))
    return sorted(mods, key=lambda m: (m["target"], m["name"]))


def refresh_mods(store: Store, gh: GitHub, now: Callable[[], str] = _now) -> None:
    checked_at = now()
    try:
        mods = fetch_playground_mods(gh)
        source = f"mod.yml on each branch of {MODS_REPO}"
    except (httpx2.HTTPError, RuntimeError) as e:
        previous = store.status["sources"].get("mods", {})
        status: Json = {"ok": False, "checked_at": checked_at, "error": str(e)}
        if previous.get("fetched_at"):
            status["fetched_at"] = previous["fetched_at"]
        store.status["sources"]["mods"] = status
        log.warning("  x mods: %s (keeping previous data)", e)
        return
    store.mods = {"fetched_at": now(), "source": source, "mods": mods}
    store.status["sources"]["mods"] = {"ok": True, "checked_at": checked_at, "fetched_at": store.mods["fetched_at"]}
    log.info("  ok mods: %d from %s", len(mods), source)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("httpx2").setLevel(logging.WARNING)
    store = load_store(DATA_DIR)
    http = client()
    refresh_mods(store, GitHub(http, os.environ.get("GITHUB_TOKEN")))
    log.info("%d files changed in data/", len(save_store(DATA_DIR, store)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
