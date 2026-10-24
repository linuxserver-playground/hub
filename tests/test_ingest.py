"""Reconcile and single-release ingest against the fake GitHub."""

import pytest

from lsio_hub.ingest import IngestError, fetch_manifests, ingest_one, parse_manifest, pending_releases, reconcile
from lsio_hub.store import Store

from .conftest import NOW, RELEASES, FakeGitHub, build_store


def test_reconcile_ingests_every_live_release() -> None:
    store = build_store()
    assert sorted(store.images) == ["multidb", "sonarr", "swag"]
    sonarr = store.images["sonarr"]
    assert sorted(sonarr.manifests) == ["develop", "master"]
    assert sorted(sonarr.builds) == ["4.0.19.2000-ls1", "4.0.20.3014-ls2", "develop-5.0.1.1234-ls1"]
    assert sonarr.latest["master"]["tag"] == "4.0.20.3014-ls2"
    assert sonarr.latest["develop"]["release_tag"] == "develop"
    assert sonarr.latest["master"]["assets"]["build.json"].endswith("/4.0.20.3014-ls2/build.json")
    assert sonarr.packages["master"]["amd64"]["tag"] == "4.0.20.3014-ls2"
    assert sonarr.packages["develop"]["arm64"]["release_tag"] == "develop"
    assert sonarr.diffs["4.0.20.3014-ls2"]["classification"] == "upstream"
    assert sonarr.diffs["4.0.20.3014-ls2"]["packages"]["amd64"]["apk"]["added"][0]["name"] == "krb5-libs"
    assert sonarr.tests["4.0.20.3014-ls2"]["amd64"]["success"] is True


def test_rejected_release_is_recorded_and_other_branches_ignored() -> None:
    store = build_store()
    rejected = store.status["rejected"]
    assert list(rejected) == ["multidb@bad-ls9"]
    assert "differs from the release tag" in rejected["multidb@bad-ls9"]["error"]
    assert rejected["multidb@bad-ls9"]["checked_at"] == NOW
    assert "feature-ls1" not in store.images["multidb"].builds
    assert store.status["sources"]["releases"] == {"ok": True, "checked_at": NOW, "fetched_at": NOW}


def test_failed_arm64_has_no_table_but_a_test_report() -> None:
    multidb = build_store().images["multidb"]
    first = multidb.builds["1.0.0-ls1"]
    assert [p["result"] for p in first["platforms"]] == ["success", "failure"]
    assert "arm64" not in multidb.layers["1.0.0-ls1"]
    assert multidb.tests["1.0.0-ls1"]["arm64"]["success"] is False
    assert multidb.diffs["1.0.0-ls2"]["classification"] == "linuxserver"


def test_second_run_is_idempotent() -> None:
    store = build_store()
    github = FakeGitHub()
    reconcile(store, github, now=lambda: NOW)
    # Only the rejected release is retried (its build.json asset); nothing already stored is downloaded again.
    assert len(github.downloads) == 1 and github.downloads[0].endswith("/build.json")
    assert list(store.status["rejected"]) == ["multidb@bad-ls9"]


def test_pending_releases_are_oldest_first_and_capped() -> None:
    store = build_store()
    sonarr = store.images["sonarr"]
    sonarr.builds.clear()
    pending = pending_releases(sonarr, RELEASES["docker-sonarr"], keep=1)
    assert [r["tag_name"] for r in pending] == ["4.0.20.3014-ls2", "develop-5.0.1.1234-ls1"]


def test_fetch_manifests_finds_live_branches() -> None:
    manifests = fetch_manifests(FakeGitHub(), "linuxserver-playground/docker-sonarr", "master")
    assert sorted(manifests) == ["develop", "master"]
    assert manifests["develop"]["release"]["tag"] == "develop"
    with pytest.raises(IngestError, match=r"no image\.yml"):
        fetch_manifests(FakeGitHub(), "linuxserver-playground/docker-nope", "master")


def test_parse_manifest_reports_contract_errors() -> None:
    with pytest.raises(IngestError, match="does not validate"):
        parse_manifest("schema: 1\nname: x\n")
    with pytest.raises(IngestError, match="not valid YAML"):
        parse_manifest("a: [")


def test_ingest_one() -> None:
    store = Store()
    github = FakeGitHub()
    assert ingest_one(store, github, "linuxserver-playground/docker-swag", "5.2.0-ls1", now=lambda: NOW)
    assert "5.2.0-ls1" in store.images["swag"].builds
    assert not ingest_one(store, github, "linuxserver-playground/docker-swag", "5.2.0-ls1", now=lambda: NOW)
    with pytest.raises(IngestError):
        ingest_one(store, github, "someone/docker-swag", "5.2.0-ls1", now=lambda: NOW)


def test_listing_failure_keeps_previous_data() -> None:
    class Broken(FakeGitHub):
        def org_repos(self, org: str) -> list[dict[str, object]]:
            raise RuntimeError("GraphQL down")

    store = build_store()
    reconcile(store, Broken(), now=lambda: "2026-10-25T00:00:00Z")
    assert sorted(store.images) == ["multidb", "sonarr", "swag"]
    status = store.status["sources"]["manifests"]
    assert status["ok"] is False and "GraphQL down" in status["error"] and status["fetched_at"] == NOW


def test_repo_failure_costs_only_that_repository() -> None:
    class Flaky(FakeGitHub):
        def releases(self, repo: str, *, max_pages: int = 3) -> list[dict[str, object]]:
            if repo.endswith("docker-swag"):
                raise IngestError("boom")
            return super().releases(repo)

    store = Store()
    reconcile(store, Flaky(), now=lambda: NOW)
    assert "sonarr" in store.images and store.images["sonarr"].builds
    assert not store.images["swag"].builds
    assert store.status["sources"]["releases"]["ok"] is False
    assert "docker-swag: boom" in store.status["sources"]["releases"]["error"]
