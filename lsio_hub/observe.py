"""
The observed poller: what GitHub says about each image right now, as opposed to what the builds reported. Stars,
the archived flag and the last push come from one GraphQL query over the organisation. Written to
data/observed.json; nothing else writes that file.

The registry is not listed: a build's tags are fixed when it publishes, and its build.json says which
(`published.tags`; `version.tags` for releases made before that field), so the ingest has them on the release path
and the builds list serves them (`BuildSummary.tags`). The hourly listing of every GHCR package this replaces took
most of this poller's time and was read by nothing.

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
from .store import Store, load_store, save_store

log = logging.getLogger(__name__)
Json = dict[str, Any]


def _now() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def observe(store: Store, gh: GitHub, now: Callable[[], str] = _now) -> None:
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
    for repo in repos:
        images[repo["name"].removeprefix("docker-")] = {
            "url": repo["url"],
            "stars": repo["stars"],
            "archived": repo["archived"],
            "pushed_at": repo.get("pushed_at"),
        }
    store.observed = {
        "fetched_at": now(),
        "images": dict(sorted(images.items())),
    }
    store.status["sources"]["observed"] = {
        "ok": True,
        "checked_at": checked_at,
        "fetched_at": store.observed["fetched_at"],
    }
    log.info("  ok observed: %d images", len(images))


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("httpx2").setLevel(logging.WARNING)
    store = load_store(DATA_DIR)
    token = os.environ.get("GITHUB_TOKEN")
    observe(store, GitHub(client(), token))
    # The vulnerability poller's status, retired with it: builds are not rescanned (the refresh owned the file).
    store.status["sources"].pop("vulnerabilities", None)
    changed = save_store(DATA_DIR, store)
    log.info("%d files changed in data/", len(changed))
    return 0


if __name__ == "__main__":
    sys.exit(main())
