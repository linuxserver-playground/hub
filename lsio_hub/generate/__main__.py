"""
Usage: python -m lsio_hub.generate [--only docs,unraid,...] [--offline] [--out DIR]

Writes every generator's output under out/ from the committed data/. `--offline` skips downloading the test
report tarballs and file trees for the build pages (they then link to the Release assets instead).
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

import httpx2

from ..config import DATA_DIR, OUT_DIR, SiteConfig
from ..fleet import hub_settings
from ..sources.http import client, request
from ..store import load_store
from . import GENERATORS, existing_paths, generate_all, write_output
from .common import make_context, no_fetch

log = logging.getLogger(__name__)


def fetcher(http: httpx2.Client, token: str | None) -> object:
    headers = {"Authorization": f"Bearer {token}"} if token else {}

    def fetch(url: str) -> bytes | None:
        try:
            return request(http, "GET", url, headers={**headers, "Accept": "application/octet-stream"}).content
        except httpx2.HTTPError as e:
            log.warning("  ! %s: %s", url, e)
            return None

    return fetch


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("httpx2").setLevel(logging.WARNING)
    parser = argparse.ArgumentParser(description="Generate every downstream artefact from data/.")
    parser.add_argument("--only", help="comma separated generator names: " + ", ".join(GENERATORS))
    parser.add_argument("--offline", action="store_true", help="do not download Release assets for build pages")
    parser.add_argument("--out", default=str(OUT_DIR))
    args = parser.parse_args(argv)
    only = set(args.only.split(",")) if args.only else None
    if only and (unknown := only - GENERATORS.keys()):
        parser.error(f"unknown generators: {', '.join(sorted(unknown))}")
    out_dir = Path(args.out)
    site = SiteConfig.from_env()
    store = load_store(DATA_DIR)
    fetch = no_fetch if args.offline else fetcher(client(), os.environ.get("GITHUB_TOKEN"))
    ctx = make_context(store, site, hub_settings(site), fetch)  # type: ignore[arg-type]
    existing = existing_paths(out_dir, "builds")
    ctx.extra["existing"] = existing
    outputs = generate_all(ctx, only)
    keep = {f"builds/{p}" for p in existing if p.split("/")[-1] != "index.html" or p.count("/") == 2}
    written = write_output(out_dir, outputs, keep=keep)
    log.info("Wrote %d files for %d images into %s", len(written), len(ctx.images), out_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
