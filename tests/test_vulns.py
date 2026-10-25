"""The vulnerability poller: grype's report reduced, the scan ledger, and the merged response."""

import copy
import gzip
import json
from pathlib import Path
from typing import Any

from lsio_hub import responses, vulns
from lsio_hub.config import SiteConfig
from lsio_hub.fleet import load_fleet
from lsio_hub.models import BuildVulnsData
from lsio_hub.observe import observe
from lsio_hub.store import Store, load_store, save_store

from .conftest import DB_DATE, GRYPE_REPORT, NOW, FakeGitHub, FakeGrype, asset_bytes, build_store, legacy_http

Json = dict[str, Any]
LATER = "2026-10-25T13:00:00.000Z"  # 25 hours after NOW


def test_compact_reduces_the_report() -> None:
    record = vulns.compact(GRYPE_REPORT)
    assert record["db_date"] == DB_DATE and record["grype_version"] == "0.121.0"
    assert set(record) == {"db_date", "grype_version", "matches"}
    rows = {(m["package"], m["id"]): m for m in record["matches"]}
    assert len(rows) == 7
    dotnet = rows[("System.Text.Json", "GHSA-8g4q-xg66-9fp4")]
    assert dotnet["severity"] == "high" and dotnet["fix_state"] == "fixed" and dotnet["fixed_in"] == ["6.0.10"]
    assert dotnet["cvss"] == 8.8  # the highest base score of the CVSS 3.1 and 4.0 vectors
    assert dotnet["urls"][0] == "https://github.com/advisories/GHSA-8g4q-xg66-9fp4" and len(dotnet["urls"]) == 6
    assert dotnet["type"] == "dotnet" and dotnet["version"] == "6.0.9"
    # Alpine findings without a fix: grype leaves the fix state empty, the hub says unknown.
    coreutils = rows[("coreutils", "CVE-2016-2781")]
    assert coreutils["fix_state"] == "unknown" and coreutils["cvss"] is None and coreutils["fixed_in"] == []
    assert rows[("zlib1g", "CVE-2023-45853")]["fix_state"] == "wont-fix"
    # Worst first, then by package.
    assert [m["severity"] for m in record["matches"]] == [
        "critical",
        "high",
        "high",
        "high",
        "medium",
        "medium",
        "medium",
    ]
    assert set(record["matches"][0]) == {
        "package",
        "version",
        "type",
        "id",
        "severity",
        "fix_state",
        "fixed_in",
        "urls",
        "cvss",
    }


def test_compact_folds_a_package_matched_at_several_paths() -> None:
    report = copy.deepcopy(GRYPE_REPORT)
    twice = copy.deepcopy(report["matches"][0])
    twice["artifact"]["id"] = "another-location"
    other_version = copy.deepcopy(report["matches"][0])
    other_version["artifact"]["version"] = "6.0.8"
    report["matches"] += [twice, other_version]
    rows = [(m["package"], m["id"], m["version"]) for m in vulns.compact(report)["matches"]]
    assert len(rows) == 8 and rows.count(("System.Text.Json", "GHSA-8g4q-xg66-9fp4", "6.0.9")) == 1
    merged = vulns.merge({"amd64": vulns.compact(report)})
    assert len(merged) == 7 and vulns.summarise(merged)["high"] == 3  # one row per id and package


def test_compact_tolerates_an_odd_report() -> None:
    record = vulns.compact(
        {
            "matches": [{"vulnerability": {"id": "X", "severity": "Weird", "fix": {"state": "n/a"}}, "artifact": {}}],
            "descriptor": {"version": "0.1.0", "db": {"built": "2026-01-01T00:00:00Z"}},
        }
    )
    assert record["db_date"] == "2026-01-01T00:00:00Z"
    assert record["matches"] == [
        {
            "package": "",
            "version": "",
            "type": "unknown",
            "id": "X",
            "severity": "unknown",
            "fix_state": "unknown",
            "fixed_in": [],
            "urls": [],
            "cvss": None,
        }
    ]


def test_summarise_and_merge() -> None:
    amd64 = vulns.compact(GRYPE_REPORT)
    arm64 = copy.deepcopy(amd64)
    arm64["matches"] = [m for m in arm64["matches"] if m["type"] != "deb"]
    merged = vulns.merge({"amd64": amd64, "arm64": arm64})
    assert len(merged) == 7
    by_key = {(m["package"], m["id"]): m["arches"] for m in merged}
    assert by_key[("zlib1g", "CVE-2023-45853")] == ["amd64"]
    assert by_key[("curl", "CVE-2026-92392")] == ["amd64", "arm64"]
    assert vulns.summarise(merged) == {
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


def test_scan_covers_the_newest_build_of_every_branch(store: Store) -> None:
    sonarr, multidb = store.images["sonarr"], store.images["multidb"]
    assert sorted(sonarr.vulns) == ["4.0.20.3014-ls2", "develop-5.0.1.1234-ls1"]
    assert sorted(sonarr.vulns["4.0.20.3014-ls2"]) == ["amd64", "arm64"]
    assert "1.0.0-ls1" not in multidb.vulns and sorted(multidb.vulns["1.0.0-ls2"]) == ["amd64", "arm64"]
    assert sonarr.vulns["4.0.20.3014-ls2"]["amd64"]["db_date"] == DB_DATE
    ledger = store.observed["vulnerabilities"]
    assert ledger["db_date"] == DB_DATE and ledger["grype_version"] == "0.121.0" and ledger["checked_at"] == NOW
    assert ledger["builds"]["sonarr@4.0.20.3014-ls2"] == {
        "scanned_at": NOW,
        "db_date": DB_DATE,
        "arches": ["amd64", "arm64"],
    }
    assert "sonarr@4.0.19.2000-ls1" not in ledger["builds"]
    status = store.status["sources"]["vulnerabilities"]
    assert status == {"ok": True, "checked_at": NOW, "fetched_at": NOW}


def test_rescan_only_when_the_database_moved_and_a_day_passed() -> None:
    grype = FakeGrype()
    store = build_store(grype=grype)
    first = len(grype.scans)
    assert first == 8 and grype.updates == 1  # four newest builds, two architectures each; one db update
    # Same database an hour later: nothing to do, and no database update either.
    vulns.scan(store, grype, asset_bytes, now=lambda: "2026-10-24T13:00:00.000Z", cache_dir=None)
    assert len(grype.scans) == first and grype.updates == 1
    # The database moved but the scans are an hour old: still nothing.
    grype._db_date = "2026-10-24T20:00:00Z"
    vulns.scan(store, grype, asset_bytes, now=lambda: "2026-10-24T13:00:00.000Z", cache_dir=None)
    assert len(grype.scans) == first
    # A day later with a newer database: everything is rescanned, after a database update.
    vulns.scan(store, grype, asset_bytes, now=lambda: LATER, cache_dir=None)
    assert len(grype.scans) == 2 * first and grype.updates == 2
    assert store.observed["vulnerabilities"]["builds"]["swag@5.2.0-ls1"]["scanned_at"] == LATER
    assert store.images["swag"].vulns["5.2.0-ls1"]["amd64"]["db_date"] == "2026-10-24T20:00:00Z"
    # A day later with the same database: nothing.
    vulns.scan(store, grype, asset_bytes, now=lambda: "2026-10-26T14:00:00.000Z", cache_dir=None)
    assert len(grype.scans) == 2 * first


def test_without_grype_nothing_is_scanned_and_status_says_so() -> None:
    github = FakeGitHub()
    store = build_store(github, FakeGrype(version=None))
    assert all(not r.vulns for r in store.images.values()) and "vulnerabilities" not in store.observed
    status = store.status["sources"]["vulnerabilities"]
    assert status["ok"] is False and "not available" in status["error"] and "fetched_at" not in status
    # Grype without a database: the same, with a different reason.
    vulns.scan(store, FakeGrype(db_date=None), asset_bytes, now=lambda: NOW, cache_dir=None)
    assert "no vulnerability database" in store.status["sources"]["vulnerabilities"]["error"]
    # The API still builds, without vulns.json files or summaries.
    fleet = load_fleet(store, SiteConfig(site_url="https://example.github.io", base_path="/hub/"))
    assert responses.vuln_routes(fleet) == []
    sonarr = store.images["sonarr"]
    assert responses.build_summary(fleet, sonarr, sonarr.builds["4.0.20.3014-ls2"]).vulnerabilities is None
    assert fleet.sources["vulnerabilities"].ok is False


def test_scan_failures_are_recorded_and_the_rest_proceeds(store: Store) -> None:
    class Flaky(FakeGrype):
        def scan(self, sbom: Path) -> Json:
            if "arm64" in sbom.name:
                raise vulns.ScanError("boom")
            return super().scan(sbom)

    def no_swag(url: str) -> bytes | None:
        return None if "/swag/" in url else asset_bytes(url)

    for record in store.images.values():
        record.vulns.clear()
    store.observed.pop("vulnerabilities", None)
    vulns.scan(store, Flaky(), no_swag, now=lambda: LATER, cache_dir=None)
    assert sorted(store.images["sonarr"].vulns["4.0.20.3014-ls2"]) == ["amd64"]
    assert "5.2.0-ls1" not in store.images["swag"].vulns
    status = store.status["sources"]["vulnerabilities"]
    assert status["ok"] is False and "swag@5.2.0-ls1 amd64: SBOM not available" in status["error"]
    assert "sonarr@4.0.20.3014-ls2 arm64: boom" in status["error"]
    assert status["fetched_at"] == LATER  # some SBOMs were scanned
    # The missing architecture is retried on the next run, whatever the clock says.
    assert vulns.due(
        store.observed["vulnerabilities"]["builds"]["sonarr@4.0.20.3014-ls2"],
        {"amd64"},
        {"amd64", "arm64"},
        DB_DATE,
        LATER,
    )


def test_sbom_cache_is_used_before_the_release(tmp_path: Path, store: Store) -> None:
    grype = FakeGrype()
    calls: list[str] = []

    def counting(url: str) -> bytes | None:
        calls.append(url)
        return asset_bytes(url)

    for record in store.images.values():
        record.vulns.clear()
    store.observed.pop("vulnerabilities", None)
    vulns.scan(store, grype, counting, now=lambda: NOW, cache_dir=tmp_path)
    cached = tmp_path / "sonarr" / "4.0.20.3014-ls2" / "packages.amd64.json.gz"
    assert cached.is_file() and json.loads(gzip.decompress(cached.read_bytes()))["artifacts"]
    downloaded = len(calls)
    # Next time nothing is fetched: a fresh database and a day later, every SBOM comes from the cache.
    grype._db_date = "2026-10-25T00:00:00Z"
    vulns.scan(store, grype, counting, now=lambda: LATER, cache_dir=tmp_path)
    assert len(calls) == downloaded and len(grype.scans) == 2 * downloaded


def test_observe_keeps_the_ledger(store: Store) -> None:
    ledger = store.observed["vulnerabilities"]
    observe(store, FakeGitHub(), legacy_http(), now=lambda: LATER)
    assert store.observed["fetched_at"] == LATER and store.observed["vulnerabilities"] == ledger


def test_vulns_files_round_trip_and_rotate(tmp_path: Path, store: Store) -> None:
    save_store(tmp_path, store)
    path = tmp_path / "images" / "sonarr" / "builds" / "4.0.20.3014-ls2.vulns.arm64.json"
    assert path.is_file() and b"\n" not in path.read_bytes().rstrip(b"\n")  # compact, like the other build files
    loaded = load_store(tmp_path)
    assert loaded.images["sonarr"].vulns == store.images["sonarr"].vulns
    del loaded.images["sonarr"].builds["4.0.20.3014-ls2"]
    save_store(tmp_path, loaded)
    assert not path.is_file()


def test_response_merges_architectures(store: Store) -> None:
    sonarr = store.images["sonarr"]
    data = responses.vulns(sonarr, "4.0.20.3014-ls2")
    assert isinstance(data, BuildVulnsData)
    assert data.db_date == DB_DATE and data.grype_version == "0.121.0" and data.caveats == vulns.CAVEATS
    assert len(data.caveats) >= 4 and all(c.endswith(".") for c in data.caveats)
    assert data.summary.model_dump() == {
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
    assert data.by_arch["arm64"].critical == 0 and data.by_arch["arm64"].wont_fix == 0
    assert data.by_arch["amd64"] == data.summary
    first = data.matches[0]
    assert first.id == "CVE-2023-45853" and first.severity == "critical" and first.arches == ["amd64"]
    curl = next(m for m in data.matches if m.package == "curl")
    assert curl.arches == ["amd64", "arm64"] and curl.fix_state == "unknown"
    assert responses.vulns(sonarr, "4.0.19.2000-ls1") is None and responses.vulns(sonarr, "nope") is None


def test_vulns_endpoint_and_builds_summary(files: dict[str, bytes]) -> None:
    body = json.loads(files["api/v1/catalog/sonarr/builds/4.0.20.3014-ls2/vulns.json"])
    data = body["data"]
    assert data["summary"]["critical"] == 1 and data["matches"][0]["arches"] == ["amd64"]
    assert "cvss" not in data["matches"][-1] or data["matches"][-1]["cvss"] is not None  # None is omitted
    assert len(data["caveats"]) == len(vulns.CAVEATS)
    builds = json.loads(files["api/v1/catalog/sonarr/builds.json"])["data"]["builds"]
    newest = next(b for b in builds if b["tag"] == "4.0.20.3014-ls2")
    assert newest["vulnerabilities"] == data["summary"]
    assert newest["links"]["vulns"].endswith("/builds/4.0.20.3014-ls2/vulns.json")
    assert "vulnerabilities" not in next(b for b in builds if b["tag"] == "4.0.19.2000-ls1")
    status = json.loads(files["api/v1/status.json"])["data"]["status"]["sources"]["vulnerabilities"]
    assert status["ok"] is True
