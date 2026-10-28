"""
Vulnerabilities: the hub keeps the counts of each build's own scan (record.json), links the build's vulns.json on its
repository's Pages, serves no copy and rescans nothing; the retired per-architecture scan files are migrated once.
"""

import copy
import json
from pathlib import Path
from typing import Any

import httpx2
from builder.derive.vulns import summary_of

from lsio_hub import responses
from lsio_hub.config import SiteConfig
from lsio_hub.fleet import load_fleet
from lsio_hub.ingest import migrate_vulns, rotate
from lsio_hub.observe import main as observe_main
from lsio_hub.observe import observe
from lsio_hub.store import Store, load_store, save_store

from .conftest import DB_DATE, NOW, FakeGitHub, own_scans, registry_http

Json = dict[str, Any]
PAGES = "https://linuxserver-playground.github.io/docker-sonarr/builds"
COUNTS = {
    "critical": 1,
    "high": 3,
    "medium": 3,
    "low": 0,
    "negligible": 0,
    "unknown": 0,
    "fixed": 4,
    "unfixed": 2,
    "wont_fix": 1,
}


def test_builds_list_carries_the_counts_and_links_the_scan_on_the_repository_pages(files: dict[str, bytes]) -> None:
    builds = json.loads(files["api/v1/catalog/sonarr/builds.json"])["data"]["builds"]
    newest = next(b for b in builds if b["tag"] == "4.0.20.3014-ls2")
    assert newest["vulnerabilities"] == COUNTS
    assert newest["links"]["vulns"] == f"{PAGES}/4.0.20.3014-ls2/vulns.json"
    older = next(b for b in builds if b["tag"] == "4.0.19.2000-ls1")  # made before its build scanned itself
    assert "vulnerabilities" not in older and "vulns" not in older["links"]
    # The hub serves no scan of its own any more, and reports no scanner status.
    assert not [path for path in files if path.endswith("/vulns.json")]
    assert "vulnerabilities" not in json.loads(files["api/v1/status.json"])["data"]["status"]["sources"]


def test_counts_are_the_shared_shaping_of_the_builds_own_scan(store: Store) -> None:
    sonarr = store.images["sonarr"]
    counts = sonarr.vulns["4.0.20.3014-ls2"]
    assert counts == summary_of(own_scans())
    assert counts["db_date"] == DB_DATE and counts["scanned_at"] == "2026-10-20T19:30:00Z"
    assert counts["by_arch"]["arm64"]["wont_fix"] == 0 and counts["by_arch"]["amd64"] == counts["summary"]
    summary = responses.vuln_summary(sonarr, "4.0.20.3014-ls2")
    assert summary is not None and summary.model_dump() == COUNTS
    assert responses.vuln_summary(sonarr, "4.0.19.2000-ls1") is None


def test_counts_round_trip_one_file_per_build_and_rotate(tmp_path: Path, store: Store) -> None:
    save_store(tmp_path, store)
    builds = tmp_path / "images" / "sonarr" / "builds"
    path = builds / "4.0.20.3014-ls2.vulns.json"
    assert path.is_file() and b"\n" not in path.read_bytes().rstrip(b"\n")  # compact, like the other build files
    assert len(path.read_bytes()) < 1024 and not list(builds.glob("*.vulns.*.json"))
    loaded = load_store(tmp_path)
    assert loaded.images["sonarr"].vulns == store.images["sonarr"].vulns
    assert "4.0.20.3014-ls2.vulns" not in loaded.images["sonarr"].builds  # not mistaken for a build
    rotate(loaded.images["sonarr"], keep=0)
    assert not loaded.images["sonarr"].vulns
    save_store(tmp_path, loaded)
    assert not path.is_file()


def _legacy(tmp_path: Path, store: Store) -> Path:
    """data/ as the retired poller left it: whole scans per architecture, no counts."""
    for record in store.images.values():
        record.vulns.clear()
    save_store(tmp_path, store)
    builds = tmp_path / "images" / "sonarr" / "builds"
    for tag in ("4.0.20.3014-ls2", "4.0.19.2000-ls1", "develop-5.0.1.1234-ls1"):
        for arch, scan in own_scans().items():
            (builds / f"{tag}.vulns.{arch}.json").write_text(json.dumps(scan, separators=(",", ":")) + "\n")
    return builds


def test_legacy_scan_files_stay_until_the_ingest_migrates_them(tmp_path: Path, store: Store) -> None:
    builds = _legacy(tmp_path, store)
    loaded = load_store(tmp_path)
    sonarr = loaded.images["sonarr"]
    assert sorted(sonarr.legacy_vulns) == ["4.0.19.2000-ls1", "4.0.20.3014-ls2", "develop-5.0.1.1234-ls1"]
    assert not sonarr.vulns
    # The hourly refresh loads and saves the store without migrating: the files are written back as they were.
    observe(loaded, FakeGitHub(), registry_http(), now=lambda: NOW)
    changed = save_store(tmp_path, loaded)
    assert not [c for c in changed if ".vulns." in c] and len(list(builds.glob("*.vulns.*.json"))) == 6


class Records(FakeGitHub):
    """Serves each release's record.json from its download URL: one with a scan, one without, one missing."""

    def __init__(self, failing: set[str] | None = None) -> None:
        super().__init__()
        self.failing = failing or set()

    def download(self, url: str) -> bytes:
        if not url.endswith("/record.json"):
            return super().download(url)
        self.downloads.append(url)
        tag = url.split("/")[-2]
        request = httpx2.Request("GET", url)
        if tag in self.failing:
            raise httpx2.HTTPStatusError("502", request=request, response=httpx2.Response(502))
        if tag == "4.0.19.2000-ls1":  # released before records
            raise httpx2.HTTPStatusError("404", request=request, response=httpx2.Response(404))
        scans = own_scans() if tag == "4.0.20.3014-ls2" else {}
        return json.dumps({"schema": 1, "image": "sonarr", "tag": tag, "vulns": scans}).encode()


def test_migration_keeps_the_counts_of_the_builds_own_scan_only(tmp_path: Path, store: Store) -> None:
    builds = _legacy(tmp_path, store)
    loaded = load_store(tmp_path)
    github = Records()
    assert migrate_vulns(loaded, github) == 3
    urls = sorted(u for u in github.downloads if u.endswith("/record.json"))
    assert urls == [
        f"https://github.com/linuxserver-playground/docker-sonarr/releases/download/{tag}/record.json"
        for tag in ("4.0.19.2000-ls1", "4.0.20.3014-ls2", "develop-5.0.1.1234-ls1")
    ]
    sonarr = loaded.images["sonarr"]
    assert not sonarr.legacy_vulns and list(sonarr.vulns) == ["4.0.20.3014-ls2"]
    assert sonarr.vulns["4.0.20.3014-ls2"] == summary_of(own_scans())
    changed = save_store(tmp_path, loaded)
    assert "images/sonarr/builds/4.0.20.3014-ls2.vulns.json" in changed
    assert not list(builds.glob("*.vulns.*.json"))
    # Done once: nothing is left to read.
    assert migrate_vulns(load_store(tmp_path), Records()) == 0


def test_migration_keeps_the_old_files_when_a_record_cannot_be_read(tmp_path: Path, store: Store) -> None:
    _legacy(tmp_path, store)
    loaded = load_store(tmp_path)
    assert migrate_vulns(loaded, Records(failing={"4.0.20.3014-ls2"})) == 2
    sonarr = loaded.images["sonarr"]
    assert list(sonarr.legacy_vulns) == ["4.0.20.3014-ls2"] and not sonarr.vulns
    assert migrate_vulns(loaded, Records()) == 1 and list(sonarr.vulns) == ["4.0.20.3014-ls2"]


def test_the_refresh_drops_the_retired_ledger_and_status(tmp_path: Path, store: Store, monkeypatch: Any) -> None:
    old = copy.deepcopy(store)
    old.observed["vulnerabilities"] = {"db_date": DB_DATE, "grype_version": "0.121.0", "checked_at": NOW, "builds": {}}
    old.status["sources"]["vulnerabilities"] = {"ok": True, "checked_at": NOW}
    save_store(tmp_path, old)
    assert (tmp_path / "status" / "vulnerabilities.json").is_file()
    monkeypatch.setattr("lsio_hub.observe.DATA_DIR", tmp_path)
    monkeypatch.setattr("lsio_hub.observe.GitHub", lambda http, token: FakeGitHub())
    monkeypatch.setattr("lsio_hub.observe.client", registry_http)
    assert observe_main() == 0
    assert "vulnerabilities" not in json.loads((tmp_path / "observed.json").read_text())
    assert not (tmp_path / "status" / "vulnerabilities.json").exists()


def test_a_fleet_without_any_scan_still_builds(store: Store) -> None:
    for record in store.images.values():
        record.vulns.clear()
    fleet = load_fleet(store, SiteConfig(site_url="https://example.github.io", base_path="/hub/"))
    sonarr = store.images["sonarr"]
    summary = responses.build_summary(fleet, sonarr, sonarr.builds["4.0.20.3014-ls2"])
    assert summary.vulnerabilities is None and summary.links.vulns is None
