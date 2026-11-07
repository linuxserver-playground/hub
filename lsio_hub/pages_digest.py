"""
The digest of a built site that tells a real change from a rebuild: `python -m lsio_hub.pages_digest dist`.

Every Deploy reconciles the organisation and stamps when it did into the data (status/manifests.json and
status/releases.json: `checked_at`, `fetched_at`), and from there into every response's `last_updated` and every
page's "refreshed" line. So two Deploys a minute apart with nothing new in between still differ in every file. The
digest hashes every file of the site, deploy.json left out, with those times blanked in each form the site renders
them (ISO, the original API's format, the pages' date), so `scripts/pages_publish.sh` pushes to gh-pages only when
something else changed. A run that changes something real publishes those times with it.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from .config import DATA_DIR
from .dates import python_timestamp
from .templating import format_timestamp

VOLATILE_SOURCES = ("manifests", "releases")
"""The status sources every Deploy refreshes, changed or not."""
BLANK = b"<volatile>"


def volatile_times(data_dir: Path = DATA_DIR) -> list[bytes]:
    """Every rendering of the times the Deploy stamps on each run, longest first so no form eats part of another."""
    found: set[str] = set()
    for source in VOLATILE_SOURCES:
        try:
            status = json.loads((data_dir / "status" / f"{source}.json").read_text())
        except (OSError, ValueError):
            continue
        for key in ("checked_at", "fetched_at"):
            value = status.get(key) if isinstance(status, dict) else None
            if isinstance(value, str) and value:
                found |= {value, python_timestamp(value), format_timestamp(value)}
    return sorted((v.encode() for v in found if v), key=len, reverse=True)


def digest(site: Path, data_dir: Path = DATA_DIR) -> str:
    times = volatile_times(data_dir)
    total = hashlib.sha256()
    for path in sorted(p for p in site.rglob("*") if p.is_file() and p.relative_to(site).as_posix() != "deploy.json"):
        body = path.read_bytes()
        for value in times:
            body = body.replace(value, BLANK)
        total.update(path.relative_to(site).as_posix().encode() + b"\0")
        total.update(hashlib.sha256(body).digest())
    return total.hexdigest()


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("usage: python -m lsio_hub.pages_digest <site dir>", file=sys.stderr)
        return 2
    print(digest(Path(args[0])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
