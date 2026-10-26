"""
The vulnerability poller: grype against the syft SBOM (`packages.<arch>.json.gz` on the Release) of the newest
build of each live branch. Part of the observed data because its clock is the vulnerability database, not the
build: the same image gets new findings as the feeds learn about them. Written to
data/images/<name>/builds/<tag>.vulns.<arch>.json (compact) with a ledger in data/observed.json; nothing else
writes those.

    GITHUB_TOKEN=... [GRYPE=/path/to/grype] python -m lsio_hub.vulns

A build is scanned when it has no scan yet, and rescanned when the database date changed, at most once per 24
hours, so the hourly deploy stays cheap. Without grype (or without its database) nothing is scanned and
status.json says so under `sources.vulnerabilities`.
"""

from __future__ import annotations

import datetime
import gzip
import json
import logging
import os
import subprocess
import sys
import tempfile
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Protocol

import httpx2

from .config import ARCHES, DATA_DIR, ROOT
from .dates import parse_iso
from .sources.http import client, request
from .store import Store, load_store, save_store

log = logging.getLogger(__name__)
Json = dict[str, Any]
Fetch = Callable[[str], bytes | None]

SEVERITIES = ("critical", "high", "medium", "low", "negligible", "unknown")
FIX_STATES = ("fixed", "not-fixed", "wont-fix", "unknown")
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


class ScanError(Exception):
    pass


class Scanner(Protocol):
    def version(self) -> str | None:
        """grype's version, or None when it cannot run."""

    def db_date(self, *, update: bool) -> str | None:
        """When the vulnerability database was built (ISO 8601), updating it first when asked; None without one."""

    def scan(self, sbom: Path) -> Json:
        """grype's JSON report for a syft document."""


class Grype:
    """The real binary. `GRYPE` names it (default: `grype` on PATH); the database lives where grype keeps it."""

    def __init__(self, binary: str | None = None) -> None:
        self.binary = binary or os.environ.get("GRYPE") or "grype"
        self.env = {**os.environ, "GRYPE_CHECK_FOR_APP_UPDATE": "false"}

    def _run(self, *args: str, check: bool = True, **env: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [self.binary, *args], capture_output=True, text=True, check=check, env={**self.env, **env}, timeout=1800
        )

    def version(self) -> str | None:
        try:
            out = json.loads(self._run("version", "-o", "json").stdout)
        except (OSError, subprocess.SubprocessError, ValueError):
            return None
        version = out.get("version")
        return str(version) if version else None

    def db_date(self, *, update: bool) -> str | None:
        """Updates when asked, or when there is no usable database at all (a runner without the cache)."""
        if update:
            self._update()
        built = self._status()
        if built is None and not update:
            self._update()
            built = self._status()
        return built

    def _update(self) -> None:
        try:
            self._run("db", "update")
        except (OSError, subprocess.SubprocessError) as e:
            log.warning("  ! grype db update failed: %s", _stderr(e))

    def _status(self) -> str | None:
        try:
            status = json.loads(self._run("db", "status", "-o", "json").stdout)
        except (OSError, subprocess.SubprocessError, ValueError):
            return None
        built = status.get("built")
        return str(built) if built and status.get("valid", True) else None

    def scan(self, sbom: Path) -> Json:
        try:
            # The database is updated by db_date(); a scan must not change it halfway through a run.
            out = self._run(f"sbom:{sbom}", "-o", "json", "-q", GRYPE_DB_AUTO_UPDATE="false").stdout
            report: Json = json.loads(out)
        except (OSError, subprocess.SubprocessError, ValueError) as e:
            raise ScanError(_stderr(e)) from e
        return report


def _stderr(e: BaseException) -> str:
    err = getattr(e, "stderr", None)
    return str(err).strip() if err else str(e)


# ---------------------------------------------------------------------------------------------------
# The compact record and its summary


def _severity(value: Any) -> str:
    text = str(value or "").lower()
    return text if text in SEVERITIES else "unknown"


def _fix_state(value: Any) -> str:
    text = str(value or "").lower()
    return text if text in FIX_STATES else "unknown"


def _cvss(entries: Any) -> float | None:
    scores = [e.get("metrics", {}).get("baseScore") for e in entries or [] if isinstance(e, dict)]
    numbers = [float(s) for s in scores if isinstance(s, int | float)]
    return max(numbers) if numbers else None


def db_date_of(report: Json) -> str | None:
    """`descriptor.db.status.built` (grype >= 0.87) or `descriptor.db.built` (older)."""
    db = report.get("descriptor", {}).get("db") or {}
    built = (db.get("status") or {}).get("built") or db.get("built")
    return str(built) if built else None


def compact(report: Json, db_date: str | None = None) -> Json:
    """
    The stored form of a grype report: one row per vulnerability, package and version (syft lists a package once
    per location, grype matches each), the database date and grype's version.
    """
    matches: dict[tuple[str, str, str], Json] = {}
    for m in report.get("matches", []):
        v, a = m.get("vulnerability", {}), m.get("artifact", {})
        fix = v.get("fix") or {}
        urls = [v["dataSource"]] if v.get("dataSource") else []
        urls += [u for u in v.get("urls") or [] if u not in urls]
        package, version, vuln_id = str(a.get("name", "")), str(a.get("version", "")), str(v.get("id", ""))
        row: Json = {
            "package": package,
            "version": version,
            "type": str(a.get("type", "unknown")),
            "id": vuln_id,
            "severity": _severity(v.get("severity")),
            "fix_state": _fix_state(fix.get("state")),
            "fixed_in": [str(x) for x in fix.get("versions") or []],
            "urls": urls,
            "cvss": _cvss(v.get("cvss")),
        }
        matches.setdefault((vuln_id, package, version), row)
    return {
        "db_date": db_date or db_date_of(report) or "",
        "grype_version": str(report.get("descriptor", {}).get("version", "")),
        "matches": sort_matches(list(matches.values())),
    }


def sort_matches(matches: list[Json]) -> list[Json]:
    return sorted(matches, key=lambda m: (SEVERITIES.index(m["severity"]), m["package"].casefold(), m["id"]))


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
    return sort_matches(list(merged.values()))


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
        if due(builds.get(key), set(store.images[name].vulns.get(tag, {})), set(urls), db_date, checked_at):
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
                return scanner.scan(path)
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
            record.vulns.setdefault(tag, {})[arch] = compact(outcome, db_date)
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
