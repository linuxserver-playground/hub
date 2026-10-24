"""
The mods index. Every branch of linuxserver-playground/docker-mods carries a mod.yml (schemas/mod.schema.json);
the hub reads them all into data/mods.json. Until that repository exists, the legacy
linuxserver/docker-mods mod-list.yml is read (never written) and converted to the same shape.

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

from .config import DATA_DIR, LEGACY_MOD_LIST_URL, LEGACY_MODS_REPO, MODS_IMAGE, MODS_REPO
from .sources.github import GitHub
from .sources.http import client, request
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
        "applies_to": [data["target"]],
        "docs": data.get("docs"),
        "source": "playground",
    }


def from_legacy(text: str) -> list[Json]:
    """
    mod-list.yml (image -> {mod name: branch url}) to mod records. The branch is `<target>-<name>`; a mod
    listed under several images (universal mods, shared code-server mods) gets them all in `applies_to`. Each
    entry is marked `source: legacy` and keeps `ghcr.io/linuxserver/mods:<branch>`, where those mods live;
    nothing is rewritten to the playground namespace.
    """
    parsed = yaml.safe_load(text) or {}
    by_branch: dict[str, Json] = {}
    for image, entry in (parsed.get("mods") or {}).items():
        for item in entry.get("container_mods", []):
            for mod_name, url in item.items():
                branch = str(url).rstrip("/").rsplit("/tree/", 1)[-1]
                target = branch[: -len(mod_name) - 1] if branch.endswith(f"-{mod_name}") else branch.split("-")[0]
                record = by_branch.setdefault(
                    branch,
                    {
                        "name": mod_name,
                        "target": target,
                        "title": mod_name,
                        "summary": f"{mod_name} mod for {target} (from the legacy mod-list.yml; no mod.yml yet).",
                        "branch": branch,
                        "url": str(url),
                        "image": f"ghcr.io/{LEGACY_MODS_REPO.split('/')[0]}/mods:{branch}",
                        "maintainers": [],
                        "platforms": ["amd64", "arm64"],
                        "bases": [],
                        "env": [],
                        "deprecated": False,
                        "deprecation_message": None,
                        "applies_to": [],
                        "docs": None,
                        "source": "legacy",
                    },
                )
                if image not in record["applies_to"]:
                    record["applies_to"].append(image)
    for record in by_branch.values():
        others = [i for i in record["applies_to"] if i != record["target"]]
        record["applies_to"] = [record["target"], *others]
    return sorted(by_branch.values(), key=lambda m: (m["target"], m["name"]))


def fetch_playground_mods(gh: GitHub) -> list[Json] | None:
    """Every branch's mod.yml, or None when the playground has no docker-mods repository yet."""
    try:
        branches = gh.paginate(f"repos/{MODS_REPO}/branches")
    except httpx2.HTTPStatusError as e:
        if e.response.status_code == 404:
            return None
        raise
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


def fetch_legacy_mods(http: httpx2.Client) -> list[Json]:
    return from_legacy(request(http, "GET", LEGACY_MOD_LIST_URL).text)


def refresh_mods(store: Store, gh: GitHub, http: httpx2.Client, now: Callable[[], str] = _now) -> None:
    checked_at = now()
    try:
        mods = fetch_playground_mods(gh)
        source = f"mod.yml on each branch of {MODS_REPO}"
        if mods is None:
            mods = fetch_legacy_mods(http)
            source = f"legacy {LEGACY_MODS_REPO} mod-list.yml (read-only; {MODS_REPO} does not exist yet)"
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
    refresh_mods(store, GitHub(http, os.environ.get("GITHUB_TOKEN")), http)
    log.info("%d files changed in data/", len(save_store(DATA_DIR, store)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
