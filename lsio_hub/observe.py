"""
The observed poller: what GitHub and the registry say about each image right now, as opposed to what the
builds reported. Stars and the archived flag come from one GraphQL query over the organisation; the GHCR
tag list from the registry API with an anonymous pull token. Written to data/observed.json; nothing else
writes that file but the vulnerability poller (vulns.py), which keeps its ledger under `vulnerabilities` and
runs after this one in `python -m lsio_hub.observe`.

    GITHUB_TOKEN=... python -m lsio_hub.observe
"""

from __future__ import annotations

import datetime
import logging
import os
import sys
from collections.abc import Callable
from typing import Any

import httpx2

from .config import DATA_DIR, ORG
from .sources.github import GitHub, is_image_repo
from .sources.http import client
from .sources.registry import ghcr_tags
from .store import Store, load_store, save_store
from .vulns import Grype, release_fetcher
from .vulns import scan as scan_vulnerabilities

log = logging.getLogger(__name__)
Json = dict[str, Any]


def _now() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def observe(store: Store, gh: GitHub, http: httpx2.Client, now: Callable[[], str] = _now) -> None:
    """Refreshes store.observed; on failure the previous data stays and status.json records why."""
    checked_at = now()
    try:
        repos = [r for r in gh.org_repos(ORG) if is_image_repo(r["name"])]
    except (httpx2.HTTPError, RuntimeError) as e:
        previous = store.status["sources"].get("observed", {})
        store.status["sources"]["observed"] = {
            "ok": False,
            "checked_at": checked_at,
            **({"fetched_at": previous["fetched_at"]} if previous.get("fetched_at") else {}),
            "error": str(e),
        }
        log.warning("  x observed: %s (keeping previous data)", e)
        return
    images: dict[str, Json] = {}
    failed: list[str] = []
    for repo in repos:
        name = repo["name"].removeprefix("docker-")
        previous = store.observed.get("images", {}).get(name, {})
        try:
            tags = ghcr_tags(http, name)
        except httpx2.HTTPError as e:
            failed.append(f"{name}: {e}")
            tags = previous.get("ghcr_tags", [])
        images[name] = {
            "url": repo["url"],
            "stars": repo["stars"],
            "archived": repo["archived"],
            "pushed_at": repo.get("pushed_at"),
            "ghcr_tags": tags,
        }
    store.observed = {
        "fetched_at": now(),
        "images": dict(sorted(images.items())),
        # The vulnerability poller's ledger (which builds were scanned against which database) belongs to it.
        **({"vulnerabilities": store.observed["vulnerabilities"]} if store.observed.get("vulnerabilities") else {}),
    }
    status: Json = {"ok": True, "checked_at": checked_at, "fetched_at": store.observed["fetched_at"]}
    if failed:
        status["error"] = "GHCR tags kept from the previous run for " + "; ".join(failed)
    store.status["sources"]["observed"] = status
    log.info("  ok observed: %d images%s", len(images), f", {len(failed)} without fresh tags" if failed else "")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("httpx2").setLevel(logging.WARNING)
    store = load_store(DATA_DIR)
    http = client()
    token = os.environ.get("GITHUB_TOKEN")
    observe(store, GitHub(http, token), http)
    scan_vulnerabilities(store, Grype(), release_fetcher(http, token))
    changed = save_store(DATA_DIR, store)
    log.info("%d files changed in data/", len(changed))
    return 0


if __name__ == "__main__":
    sys.exit(main())
