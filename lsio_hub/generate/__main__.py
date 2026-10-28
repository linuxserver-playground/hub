"""
Usage: python -m lsio_hub.generate [--only docs,unraid,...] [--out DIR]

Writes every generator's output under out/ from the committed data/. Nothing is downloaded: the heavy files of each
build are on its image repository's own Pages, which the build report pages link to. `--offline` is still accepted,
and changes nothing.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from ..config import DATA_DIR, OUT_DIR, SiteConfig
from ..fleet import hub_settings
from ..store import load_store
from . import GENERATORS, generate_all, write_output
from .common import make_context

log = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description="Generate every downstream artefact from data/.")
    parser.add_argument("--only", help="comma separated generator names: " + ", ".join(GENERATORS))
    parser.add_argument("--offline", action="store_true", help="no effect: the generators download nothing")
    parser.add_argument("--out", default=str(OUT_DIR))
    args = parser.parse_args(argv)
    only = set(args.only.split(",")) if args.only else None
    if only and (unknown := only - GENERATORS.keys()):
        parser.error(f"unknown generators: {', '.join(sorted(unknown))}")
    out_dir = Path(args.out)
    site = SiteConfig.from_env()
    ctx = make_context(load_store(DATA_DIR), site, hub_settings(site))
    written = write_output(out_dir, generate_all(ctx, only))
    log.info("Wrote %d files for %d images into %s", len(written), len(ctx.images), out_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
