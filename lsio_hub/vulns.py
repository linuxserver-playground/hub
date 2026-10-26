"""
The vulnerability poller: grype against the syft SBOM (`packages.<arch>.json.gz` on the Release) of the newest
build of each live branch. Part of the observed data because its clock is the vulnerability database, not the
build: the same image gets new findings as the feeds learn about them. Written to
data/images/<name>/builds/<tag>.vulns.<arch>.json (compact) with a ledger in data/observed.json.

    GITHUB_TOKEN=... [GRYPE=/path/to/grype] python -m lsio_hub.vulns

A build scans itself (record.json, written in its publish job), and the ingest stores that scan; this poller then
only rescans when the database date changed, at most once per 24 hours, so the hourly refresh stays cheap. A
build without a scan of its own (an older release, a failed scan) is scanned here at once. Without grype (or
without its database) nothing is scanned and data/status/vulnerabilities.json says so. grype and the stored form
of its report are the builder's (`builder.derive.vulns`), shared with the build.
"""

from __future__ import annotations

import datetime
import gzip
import logging
import os
import sys
import tempfile
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import httpx2
from builder.derive.vulns import (
    FIX_STATES,
    SEVERITIES,
    Grype,
    ScanError,
    Scanner,
    compact,
    sort_matches,
)

from .config import ARCHES, DATA_DIR, ROOT
from .dates import parse_iso
from .sources.http import client, request
from .store import Store, load_store, save_store

__all__ = [
    "CAVEATS",
    "FIX_STATES",
    "SEVERITIES",
    "Grype",
    "ScanError",
    "Scanner",
    "compact",
    "merge",
    "scan",
    "summarise",
]

log = logging.getLogger(__name__)
Json = dict[str, Any]
Fetch = Callable[[str], bytes | None]

RESCAN_AFTER = datetime.timedelta(hours=24)
"""How long a scan stands once the database date has changed (a new build is scanned at once)."""
DB_UPDATE_AFTER = datetime.timedelta(hours=24)
"""How often the poller asks grype to update its database."""
CACHE_DIR = Path(os.environ.get("VULNS_CACHE_DIR") or ROOT / ".cache" / "sboms")
"""Downloaded SBOMs, by image, tag and arch; never committed."""
WORKERS = int(os.environ.get("VULNS_WORKERS") or min(4, os.cpu_count() or 1))
"""grype processes at once. A scan is one CPU-bound process of about 150 MB, about 11 s on a runner, so a burst of
releases (66 SBOMs in one run of the base image case study) took 12 minutes one at a time."""

CAVEATS = [
    "Counts are the scanner's output (grype against the build's syft SBOM), not an assessment: they change when the "
    "vulnerability database changes, not only when the image does.",
    "Distribution packages (apk, deb) are matched against the distribution's own security feed, which knows about "
    'backported fixes: a fix state of "fixed" means the distribution ships a fixed package version, "not-fixed" '
    "means no fix exists upstream for that distribution release.",
    "Images are rebuilt weekly, so a distribution fix reaches the image within a week of the distribution shipping "
    'it; a "fixed" finding on the newest build means the rebuild has not happened yet.',
    "Unfixable findings are not a reason to avoid an image: every image on the same base shares them, and only the "
    "distribution can resolve them.",
    "A finding against a package does not mean the vulnerable code path is reachable in this image.",
]


def _now() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _age(since: str | None, now: str) -> datetime.timedelta | None:
    a, b = parse_iso(since), parse_iso(now)
    return b - a if a and b else None


# ---------------------------------------------------------------------------------------------------
# grype


def _seeded(scans: dict[str, Json] | None) -> Json | None:
    """A ledger entry for a build that scanned itself: its scans carry the database date and when they ran."""
    if not scans or not all(scan.get("scanned_at") for scan in scans.values()):
        return None
    dates = {scan.get("db_date") for scan in scans.values()}
    return {
        "scanned_at": min(str(scan["scanned_at"]) for scan in scans.values()),
        "db_date": dates.pop() if len(dates) == 1 else None,
        "arches": sorted(scans),
    }


def summarise(matches: list[Json]) -> Json:
    """Counts per severity and fix state. `unfixed` is everything that is neither fixed nor won't-fix."""
    summary = dict.fromkeys(SEVERITIES, 0) | {"fixed": 0, "unfixed": 0, "wont_fix": 0}
    for m in matches:
        summary[m["severity"]] += 1
        state = m["fix_state"]
        summary["fixed" if state == "fixed" else "wont_fix" if state == "wont-fix" else "unfixed"] += 1
    return summary


def merge(scans: dict[str, Json]) -> list[Json]:
    """
    One row per vulnerability and package across architectures (the first version seen stands), each carrying the
    `arches` it was found on. Summaries count these rows, per architecture too, so the numbers add up.
    """
    merged: dict[tuple[str, str], Json] = {}
    for arch in sorted(scans):
        for m in scans[arch].get("matches", []):
            key = (m["id"], m["package"])
            if key in merged:
                if arch not in merged[key]["arches"]:
                    merged[key]["arches"].append(arch)
            else:
                merged[key] = {**m, "arches": [arch]}
    rows: list[Json] = sort_matches(list(merged.values()))
    return rows


# ---------------------------------------------------------------------------------------------------
# The poll


def _sbom(name: str, tag: str, arch: str, url: str, fetch: Fetch, cache_dir: Path | None) -> bytes | None:
    """The gzipped syft document: the local copy when there is one, else the Release asset (kept in the cache)."""
    cached = cache_dir / name / tag / f"packages.{arch}.json.gz" if cache_dir else None
    if cached and cached.is_file():
        return cached.read_bytes()
    data = fetch(url)
    if data is not None and cached:
        cached.parent.mkdir(parents=True, exist_ok=True)
        cached.write_bytes(data)
    return data


def targets(store: Store) -> list[tuple[str, str, dict[str, str]]]:
    """(image, tag, {arch: SBOM url}) for the newest build of every live branch that the hub holds."""
    out = []
    for name, record in sorted(store.images.items()):
        for branch in sorted(record.latest):
            entry = record.latest[branch]
            tag = entry.get("tag")
            if not tag or tag not in record.builds or branch not in record.manifests:
                continue
            assets = entry.get("assets") or {}
            urls = {a: assets[f"packages.{a}.json.gz"] for a in ARCHES if assets.get(f"packages.{a}.json.gz")}
            if urls:
                out.append((name, tag, urls))
    return out


def due(entry: Json | None, have: set[str], want: set[str], db_date: str, now: str) -> bool:
    """A new build (or a new architecture) is scanned at once; a known one when the database moved, daily."""
    if not entry or not want <= have:
        return True
    if entry.get("db_date") == db_date:
        return False
    age = _age(entry.get("scanned_at"), now)
    return age is None or age >= RESCAN_AFTER


def scan(
    store: Store,
    scanner: Scanner,
    fetch: Fetch,
    now: Callable[[], str] = _now,
    cache_dir: Path | None = CACHE_DIR,
    workers: int | None = None,
) -> int:
    """Scans what is due; returns how many SBOMs were scanned. status.json records the outcome either way."""
    checked_at = now()
    previous = store.status["sources"].get("vulnerabilities", {})
    ledger: Json = dict(store.observed.get("vulnerabilities") or {})
    kept = {"fetched_at": previous["fetched_at"]} if previous.get("fetched_at") else {}

    def fail(error: str) -> int:
        store.status["sources"]["vulnerabilities"] = {"ok": False, "checked_at": checked_at, **kept, "error": error}
        log.warning("  x vulnerabilities: %s", error)
        return 0

    version = scanner.version()
    if version is None:
        return fail("grype is not available; nothing scanned")
    checked_db = _age(ledger.get("checked_at"), checked_at)
    db_date = scanner.db_date(update=checked_db is None or checked_db >= DB_UPDATE_AFTER)
    for error in getattr(scanner, "errors", []):
        log.warning("  ! %s", error)
    if db_date is None:
        return fail(f"grype {version} has no vulnerability database; nothing scanned")

    builds: dict[str, Json] = dict(ledger.get("builds") or {})
    live = set()
    scanned = 0
    failed: list[str] = []
    pending: list[tuple[str, str, str, dict[str, str]]] = []
    for name, tag, urls in targets(store):
        key = f"{name}@{tag}"
        live.add(key)
        held = store.images[name].vulns.get(tag, {})
        entry = builds.get(key) or _seeded(held)
        if entry and key not in builds:
            builds[key] = entry  # the build's own scan, stored by the ingest
        if due(entry, set(held), set(urls), db_date, checked_at):
            pending.append((key, name, tag, urls))
    with tempfile.TemporaryDirectory(prefix="lsio-hub-sbom-") as tmp:
        # Downloads stay one at a time; the scans, which are most of a release run, run side by side.
        outcomes: dict[tuple[str, str], Json | str] = {}
        jobs: list[tuple[tuple[str, str], Path]] = []
        for key, name, tag, urls in pending:
            for arch, url in sorted(urls.items()):
                data = _sbom(name, tag, arch, url, fetch, cache_dir)
                if data is None:
                    outcomes[key, arch] = "SBOM not available"
                    continue
                path = Path(tmp) / key / f"packages.{arch}.json"
                try:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(gzip.decompress(data))
                except OSError as e:
                    outcomes[key, arch] = str(e)
                    continue
                jobs.append(((key, arch), path))

        def run(path: Path) -> Json | str:
            try:
                report: Json = scanner.scan(path)
                return report
            except (OSError, ScanError) as e:
                return str(e)

        with ThreadPoolExecutor(max_workers=workers or WORKERS) as pool:
            outcomes.update(zip((job for job, _ in jobs), pool.map(run, (path for _, path in jobs)), strict=True))

    for key, name, tag, urls in pending:
        record = store.images[name]
        for arch in sorted(urls):
            outcome = outcomes[key, arch]
            if isinstance(outcome, str):
                failed.append(f"{key} {arch}: {outcome}")
                continue
            record.vulns.setdefault(tag, {})[arch] = compact(outcome, db_date, now())
            scanned += 1
        builds[key] = {"scanned_at": now(), "db_date": db_date, "arches": sorted(record.vulns.get(tag, {}))}
        log.info("  ok vulnerabilities: %s (%s)", key, ", ".join(sorted(record.vulns.get(tag, {}))) or "no SBOM")
    for record in store.images.values():
        for tag in [t for t in record.vulns if t not in record.builds]:
            del record.vulns[tag]
    store.observed["vulnerabilities"] = {
        "db_date": db_date,
        "grype_version": version,
        "checked_at": checked_at,
        "builds": {k: v for k, v in sorted(builds.items()) if k in live},
    }
    status: Json = {"ok": not failed, "checked_at": checked_at, **kept}
    if scanned or not failed:
        status["fetched_at"] = now()
    if failed:
        status["error"] = "; ".join(failed)
    store.status["sources"]["vulnerabilities"] = status
    log.info("  ok vulnerabilities: %d SBOMs scanned, database of %s", scanned, db_date)
    return scanned


def release_fetcher(http: httpx2.Client, token: str | None) -> Fetch:
    headers = {"Authorization": f"Bearer {token}"} if token else {}

    def fetch(url: str) -> bytes | None:
        try:
            return request(http, "GET", url, headers={**headers, "Accept": "application/octet-stream"}).content
        except httpx2.HTTPError as e:
            log.warning("  ! %s: %s", url, e)
            return None

    return fetch


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("httpx2").setLevel(logging.WARNING)
    store = load_store(DATA_DIR)
    scan(store, Grype(), release_fetcher(client(), os.environ.get("GITHUB_TOKEN")))
    changed = save_store(DATA_DIR, store)
    log.info("%d files changed in data/", len(changed))
    return 0


if __name__ == "__main__":
    sys.exit(main())
