"""Reconcile and single-release ingest against the fake GitHub."""

import json
from pathlib import Path

import pytest

from lsio_hub.ingest import (
    IngestError,
    fetch_manifests,
    guess_branch,
    ingest_one,
    parse_manifest,
    pending_releases,
    reconcile,
    validate_bundle,
)
from lsio_hub.sources.github import FileKey
from lsio_hub.store import Store

from .conftest import FIXTURES, NOW, RELEASES, FakeGitHub, Json, asset_bytes, build_store

SONARR_LS2_BASE = "sha256:" + "b" * 64


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


def test_rejected_releases_are_recorded() -> None:
    store = build_store()
    rejected = store.status["rejected"]
    # bad-ls9 carries a bundle for another tag; feature-ls1 is a release on a dev branch (target_commitish can't
    # be trusted, so its bundle is fetched and then rejected the same way).
    assert sorted(rejected) == ["multidb@bad-ls9", "multidb@feature-ls1"]
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
    assert reconcile(store, github, now=lambda: NOW) == []
    # Nothing already stored is downloaded again, and the rejected releases wait a day.
    assert github.downloads == []
    assert reconcile(store, github, now=lambda: "2026-10-25T12:00:00.000Z") == ["linuxserver-playground/docker-multidb"]
    assert len(github.downloads) == 2 and all(url.endswith("/build.json") for url in github.downloads)
    assert sorted(store.status["rejected"]) == ["multidb@bad-ls9", "multidb@feature-ls1"]


def test_a_rejected_release_is_retried_when_the_manifests_change() -> None:
    store = build_store()
    store.images["multidb"].manifests["master"]["description"] = "changed since the last run"
    github = FakeGitHub()
    assert reconcile(store, github, now=lambda: NOW) == ["linuxserver-playground/docker-multidb"]
    assert len(github.downloads) == 2


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
        def file_text(self, repo: str, path: str, ref: str) -> str | None:
            if repo.endswith("docker-swag"):
                raise IngestError("boom")
            return super().file_text(repo, path, ref)

    store = Store()
    reconcile(store, Flaky(), now=lambda: NOW)
    assert "sonarr" in store.images and store.images["sonarr"].builds
    assert not store.images["swag"].builds
    assert store.status["sources"]["releases"]["ok"] is False
    assert "docker-swag: boom" in store.status["sources"]["releases"]["error"]


def test_real_release_assets_ingest() -> None:
    """The first live sonarr release (2026-10-24): target_commitish is a sha, so the branch comes from the bundle."""
    real = FIXTURES / "release"

    class Real(FakeGitHub):
        def releases(self, repo: str, *, max_pages: int = 3) -> list[dict[str, object]]:
            if not repo.endswith("docker-sonarr"):
                return []
            assets = [
                {
                    "name": p.name,
                    "url": f"https://real.test/{p.name}",
                    "browser_download_url": f"https://real.test/{p.name}",
                }
                for p in sorted(real.iterdir())
            ]
            return [
                {
                    "tag_name": "4.0.20.3014-ls1",
                    "target_commitish": "42585b63d894096a69229839a8b5321c03e99efd",
                    "draft": False,
                    "prerelease": False,
                    "created_at": "2026-10-24T20:39:10Z",
                    "html_url": "https://github.com/linuxserver-playground/docker-sonarr/releases/tag/4.0.20.3014-ls1",
                    "assets": assets,
                }
            ]

        def download(self, url: str) -> bytes:
            return (real / url.rsplit("/", 1)[1]).read_bytes()

    store = Store()
    reconcile(store, Real(), now=lambda: NOW)
    sonarr = store.images["sonarr"]
    assert list(sonarr.builds) == ["4.0.20.3014-ls1"]
    assert sonarr.builds["4.0.20.3014-ls1"]["branch"] == "master"
    assert sonarr.latest["master"]["release_tag"] == "latest"
    assert sonarr.layers["4.0.20.3014-ls1"]["amd64"][0]["created_by"] == "COPY /root-out/ /"
    assert sonarr.tests["4.0.20.3014-ls1"]["amd64"]["tests"][0]["name"] == "Container startup"
    assert sonarr.diffs["4.0.20.3014-ls1"]["classification"] == "initial"
    assert not sonarr.packages  # no packages asset among the fixtures: no table, no error
    assert store.status["rejected"] == {}


def test_guess_branch_prefers_target_then_tag_prefix() -> None:
    sonarr = build_store().images["sonarr"]
    assert guess_branch(sonarr, {"target_commitish": "develop", "tag_name": "x"}) == "develop"
    assert guess_branch(sonarr, {"target_commitish": "abc123", "tag_name": "develop-5.0.0.1-ls1"}) == "develop"
    assert guess_branch(sonarr, {"target_commitish": "abc123", "tag_name": "4.0.20.3014-ls1"}) == "master"


def test_bundle_for_a_non_live_branch_is_rejected() -> None:
    store = build_store()
    sonarr = store.images["sonarr"]
    release = {"tag_name": "4.0.20.3014-ls2", "target_commitish": "x"}
    with pytest.raises(IngestError, match="not a live branch"):
        validate_bundle({**sonarr.builds["4.0.20.3014-ls2"], "branch": "feature"}, release, "sonarr", {"master"})


def test_ingest_one_without_a_release_is_a_no_op() -> None:
    """A dispatch for a run that released nothing must not fail the deploy (FakeGitHub answers 404)."""
    store = Store()
    assert ingest_one(store, FakeGitHub(), "linuxserver-playground/docker-swag", "9.9.9-ls1", now=lambda: NOW) is False
    assert "swag" not in store.images or "9.9.9-ls1" not in store.images["swag"].builds


def test_reconcile_on_an_empty_store_ingests_everything() -> None:
    store = Store()
    ingested = reconcile(store, FakeGitHub(), now=lambda: NOW)
    assert ingested == [
        "linuxserver-playground/docker-multidb",
        "linuxserver-playground/docker-sonarr",
        "linuxserver-playground/docker-swag",
    ]
    assert sorted(store.images["sonarr"].builds) == ["4.0.19.2000-ls1", "4.0.20.3014-ls2", "develop-5.0.1.1234-ls1"]
    assert store.status["sources"]["releases"]["ok"] is True


def test_reconcile_fetches_only_what_is_new() -> None:
    class Counting(FakeGitHub):
        rest_listings = 0
        rest_files = 0

        def releases(self, repo: str, *, max_pages: int = 3) -> list[Json]:
            self.rest_listings += 1
            return super().releases(repo, max_pages=max_pages)

        def file_texts(self, files: list[FileKey], *, batch: int = 25, workers: int = 8) -> dict[FileKey, str | None]:
            texts = super().file_texts(files, batch=batch, workers=workers)
            self.rest_files -= len(texts)  # served by the batch, not by REST
            return texts

        def file_text(self, repo: str, path: str, ref: str) -> str | None:
            self.rest_files += 1
            return super().file_text(repo, path, ref)

    store = build_store()
    github = Counting()
    assert reconcile(store, github, now=lambda: NOW) == []
    assert github.downloads == [] and github.listings == 1
    assert github.rest_files == 0 and github.batched >= 4  # every image.yml came from the batch
    # A release the hub lost (a dropped event): it comes back, and only its assets are downloaded.
    store.images["sonarr"].builds.pop("4.0.20.3014-ls2")
    assert reconcile(store, github, now=lambda: NOW) == ["linuxserver-playground/docker-sonarr"]
    assert "4.0.20.3014-ls2" in store.images["sonarr"].builds
    assert github.downloads and all("/sonarr/4.0.20.3014-ls2/" in url for url in github.downloads)


def test_reconcile_falls_back_to_rest_without_graphql() -> None:
    class NoGraphQL(FakeGitHub):
        def org_releases(self, org: str, *, per_repo: int = 30) -> dict[str, list[Json]]:
            raise RuntimeError("GitHub GraphQL: down")

        def file_texts(self, files: list[FileKey], *, batch: int = 25, workers: int = 8) -> dict[FileKey, str | None]:
            raise RuntimeError("GitHub GraphQL: down")

    store = build_store()
    store.images["sonarr"].builds.pop("4.0.20.3014-ls2")
    assert reconcile(store, NoGraphQL(), now=lambda: NOW) == ["linuxserver-playground/docker-sonarr"]
    assert "4.0.20.3014-ls2" in store.images["sonarr"].builds
    assert sorted(store.images["sonarr"].manifests) == ["develop", "master"]


def test_deep_reconcile_lists_every_release_over_rest() -> None:
    class Counting(FakeGitHub):
        rest_listings = 0

        def releases(self, repo: str, *, max_pages: int = 3) -> list[Json]:
            self.rest_listings += 1
            return super().releases(repo, max_pages=max_pages)

    github = Counting()
    reconcile(build_store(), github, now=lambda: NOW, deep=True)
    assert github.listings == 0 and github.rest_listings == 3


def _record_for(tmp: Path, bundle_: Json, previous: Json | None, *, vulns: bool = True) -> bytes:
    """What `builder record` writes for a fixture release, from the fixture assets."""
    from builder.derive.record import build_record

    def write(directory: Path, b: Json) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        for asset in b["assets"]:
            data = asset_bytes(asset["url"])
            if data is not None:
                (directory / asset["name"]).write_bytes(data)

    out, prev = tmp / "out", tmp / "prev"
    write(out, bundle_)
    if previous:
        write(prev, previous)

    class Scanner:
        def version(self) -> str:
            return "0.121.0"

        def db_date(self, *, update: bool) -> str:
            return NOW

        def scan(self, sbom: Path) -> Json:
            return {"descriptor": {"version": "0.121.0"}, "matches": []}

    platforms = {"amd64": {"digest": None, "layers": ["sha256:x"]}}
    base = {"image": bundle_["base"]["image"], "digest": bundle_["base"]["digest"], "platforms": platforms}
    derived = build_record(
        out,
        previous=prev if previous else None,
        scanner=Scanner() if vulns else None,
        fetch_base=lambda image, digest: base,
        now=lambda: NOW,
    )
    return json.dumps(derived).encode()


class WithRecords(FakeGitHub):
    """The fixture releases, each with the record.json its build would have attached."""

    def __init__(self, records: dict[str, bytes]) -> None:
        super().__init__()
        self.records = records

    def releases(self, repo: str, *, max_pages: int = 3) -> list[Json]:
        out = []
        for release in super().releases(repo, max_pages=max_pages):
            image = repo.split("/")[1].removeprefix("docker-")
            key = f"{image}@{release['tag_name']}"
            if key in self.records:
                url = f"https://records.test/{key}/record.json"
                release = {**release, "assets": [*release["assets"], {"name": "record.json", "url": url}]}
            out.append(release)
        return out

    def download(self, url: str) -> bytes:
        if url.startswith("https://records.test/"):
            self.downloads.append(url)
            return self.records[url.split("/")[3]]
        return super().download(url)


@pytest.fixture
def records(tmp_path: Path) -> dict[str, bytes]:
    from .conftest import SONARR_DEV, SONARR_LS1, SONARR_LS2, SWAG_LS1

    return {
        "sonarr@4.0.19.2000-ls1": _record_for(tmp_path / "a", SONARR_LS1, None),
        "sonarr@4.0.20.3014-ls2": _record_for(tmp_path / "b", SONARR_LS2, SONARR_LS1),
        "sonarr@develop-5.0.1.1234-ls1": _record_for(tmp_path / "c", SONARR_DEV, None),
        "swag@5.2.0-ls1": _record_for(tmp_path / "d", SWAG_LS1, None, vulns=False),
    }


def test_a_release_with_a_record_needs_two_downloads(records: dict[str, bytes]) -> None:
    store = Store()
    github = WithRecords(records)
    reconcile(store, github, now=lambda: NOW)
    sonarr_downloads = [u.rsplit("/", 1)[1] for u in github.downloads if "sonarr" in u]
    assert sorted(sonarr_downloads) == sorted(["build.json", "record.json"] * 3)
    # The same data as deriving it from the assets.
    legacy = build_store().images["sonarr"]
    sonarr = store.images["sonarr"]
    assert sonarr.builds == legacy.builds and sonarr.diffs == legacy.diffs
    assert sonarr.tests == legacy.tests and sonarr.layers == legacy.layers and sonarr.packages == legacy.packages
    # The build's scan and base layers are kept, so the poller and the registry have nothing to do for it.
    assert sonarr.vulns["4.0.20.3014-ls2"]["amd64"]["scanned_at"] == NOW
    assert store.bases[SONARR_LS2_BASE]["platforms"]["amd64"]["layers"] == ["sha256:x"]


def test_an_unusable_record_is_ignored(records: dict[str, bytes]) -> None:
    broken = {**records, "sonarr@4.0.20.3014-ls2": b'{"schema": 1}'}
    store = Store()
    reconcile(store, WithRecords(broken), now=lambda: NOW)
    legacy = build_store().images["sonarr"]
    assert store.images["sonarr"].diffs["4.0.20.3014-ls2"] == legacy.diffs["4.0.20.3014-ls2"]
    assert store.images["sonarr"].packages == legacy.packages


def test_the_poller_does_not_scan_a_build_again_that_scanned_itself(records: dict[str, bytes]) -> None:
    from lsio_hub import vulns

    from .conftest import FakeGrype

    store = Store()
    reconcile(store, WithRecords(records), now=lambda: NOW)
    later = "2026-10-24T13:00:00.000Z"
    vulns.scan(store, FakeGrype(), asset_bytes, now=lambda: later, cache_dir=None)
    ledger = store.observed["vulnerabilities"]["builds"]
    # sonarr's builds scanned themselves; swag's and multidb's did not, so they are scanned here.
    assert ledger["sonarr@4.0.20.3014-ls2"] == {"scanned_at": NOW, "db_date": NOW, "arches": ["amd64", "arm64"]}
    assert ledger["sonarr@develop-5.0.1.1234-ls1"]["scanned_at"] == NOW
    assert ledger["swag@5.2.0-ls1"]["scanned_at"] == later and ledger["multidb@1.0.0-ls2"]["scanned_at"] == later
