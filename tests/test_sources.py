"""The observer, the mods fetcher and the registry client."""

import json

import httpx2
import pytest

from lsio_hub import mods
from lsio_hub.ingest import refresh_bases
from lsio_hub.observe import observe
from lsio_hub.sources.github import GitHub
from lsio_hub.sources.registry import base_layers, ghcr_tags, parse_reference
from lsio_hub.store import Store

from .conftest import (
    BASE_DIGEST,
    FIXTURES,
    MOD_YMLS,
    NOW,
    UNKNOWN_BASE_DIGEST,
    FakeGitHub,
    Json,
    build_store,
    layer_digest,
    registry_http,
)


def test_observe_records_stars_archived_and_tags() -> None:
    store = build_store()
    sonarr = store.observed["images"]["sonarr"]
    assert sonarr["stars"] == 7 and sonarr["archived"] is False
    assert sonarr["ghcr_tags"] == ["4.0.20.3014-ls2", "amd64-latest", "latest"]
    assert store.observed["images"]["multidb"]["ghcr_tags"] == []  # package not published yet
    assert "builder" not in store.observed["images"]
    assert store.status["sources"]["observed"]["ok"] is True


def test_observe_failure_keeps_previous_data() -> None:
    class Broken(FakeGitHub):
        def org_repos(self, org: str) -> list[dict[str, object]]:
            raise RuntimeError("down")

    store = build_store()
    observe(store, Broken(), registry_http(), now=lambda: "2026-10-25T00:00:00Z")
    assert store.observed["images"]["sonarr"]["stars"] == 7
    status = store.status["sources"]["observed"]
    assert status == {"ok": False, "checked_at": "2026-10-25T00:00:00Z", "fetched_at": NOW, "error": "down"}


def test_ghcr_tags_follow_link_header() -> None:
    def handle(request: httpx2.Request) -> httpx2.Response:
        if request.url.path == "/token":
            return httpx2.Response(200, json={"token": "t"})
        assert request.headers["authorization"] == "Bearer t"
        if "last=" in str(request.url):
            return httpx2.Response(200, json={"tags": ["c"]})
        return httpx2.Response(
            200,
            json={"tags": ["b", "a"]},
            headers={"link": '</v2/linuxserver-playground/x/tags/list?n=1000&last=b>; rel="next"'},
        )

    assert ghcr_tags(httpx2.Client(transport=httpx2.MockTransport(handle)), "x") == ["a", "b", "c"]


def test_mods_from_each_branch() -> None:
    store = Store()
    mods.refresh_mods(store, FakeGitHub(), now=lambda: NOW)
    assert store.mods["source"].startswith("mod.yml on each branch")
    by_branch = {m["branch"]: m for m in store.mods["mods"]}
    assert set(by_branch) == set(MOD_YMLS)  # master and template are not mods
    git = by_branch["universal-git"]
    assert git["name"] == "git" and git["image"] == "ghcr.io/linuxserver-playground/mods:universal-git"
    assert git["source"] == "playground"
    assert git["env"] == [{"name": "GIT_USER", "description": "Commit author", "default": "abc", "required": False}]
    assert git["platforms"] == ["amd64", "arm64"] and git["applies_to"] == ["universal"]
    assert by_branch["universal-docker"]["applies_to"] == [
        "universal",
        "code-server",
        "openvscode-server",
        "vscodium-web",
    ]
    assert by_branch["radarr-striptracks"]["applies_to"] == ["radarr", "sonarr"]
    reload = by_branch["swag-auto-reload"]
    assert reload["deprecated"] is True and "SWAG image" in reload["deprecation_message"]


def test_mods_failure_keeps_previous() -> None:
    class Broken(FakeGitHub):
        def paginate(self, path: str, *, per_page: int = 100, max_pages: int = 10, **params: object) -> list[Json]:
            request = httpx2.Request("GET", path)
            raise httpx2.HTTPStatusError("500", request=request, response=httpx2.Response(500, request=request))

    store = build_store()
    mods.refresh_mods(store, Broken(), now=lambda: "2026-10-25T00:00:00Z")
    assert len(store.mods["mods"]) == len(MOD_YMLS)
    assert store.status["sources"]["mods"]["ok"] is False and store.status["sources"]["mods"]["fetched_at"] == NOW


def test_org_repos_reads_stars_from_the_graphql_response() -> None:
    """Stars come from `stargazerCount`; a fixture response with non-zero counts must end up in observed.json."""
    fixture = json.loads((FIXTURES / "graphql-repositories.json").read_text())
    queries: list[dict[str, object]] = []

    def handle(request: httpx2.Request) -> httpx2.Response:
        assert request.method == "POST" and request.url.path == "/graphql"
        assert request.headers["authorization"] == "Bearer t"
        queries.append(json.loads(request.content))
        return httpx2.Response(200, json=fixture)

    gh = GitHub(httpx2.Client(transport=httpx2.MockTransport(handle)), "t")
    repos = gh.org_repos("linuxserver-playground")
    assert [(r["name"], r["stars"], r["archived"], r["default_branch"]) for r in repos] == [
        ("builder", 5, False, "main"),
        ("docker-sonarr", 42, False, "master"),
        ("docker-swag", 3, True, "main"),
    ]
    assert queries[0]["variables"] == {"org": "linuxserver-playground", "cursor": None}
    assert "stargazerCount" in str(queries[0]["query"])
    store = Store()
    observe(store, gh, registry_http(), now=lambda: NOW)
    assert store.observed["images"]["sonarr"]["stars"] == 42 and store.observed["images"]["swag"]["stars"] == 3
    assert "builder" not in store.observed["images"]
    assert store.observed["fetched_at"] == NOW


def test_base_layers_from_an_index() -> None:
    base = base_layers(registry_http(), "ghcr.io/linuxserver/baseimage-alpine:3.24", BASE_DIGEST)
    assert base["digest"] == BASE_DIGEST and sorted(base["platforms"]) == ["amd64", "arm64"]
    assert base["platforms"]["amd64"]["layers"] == [layer_digest(0)]
    with pytest.raises(httpx2.HTTPStatusError):
        base_layers(registry_http(), "ghcr.io/linuxserver/baseimage-alpine:3.24", UNKNOWN_BASE_DIGEST)


def test_base_layers_from_a_single_manifest() -> None:
    def handle(request: httpx2.Request) -> httpx2.Response:
        if request.url.path == "/token":
            assert request.url.params["scope"] == "repository:linuxserver/baseimage-ubuntu:pull"
            return httpx2.Response(200, json={"token": "t"})
        assert request.url.path == "/v2/linuxserver/baseimage-ubuntu/manifests/noble"
        assert "application/vnd.oci.image.index.v1+json" in request.headers["accept"]
        return httpx2.Response(
            200,
            json={
                "mediaType": "application/vnd.oci.image.manifest.v1+json",
                "config": {"digest": "sha256:c"},
                "layers": [{"digest": "sha256:1"}, {"digest": "sha256:2"}],
            },
        )

    base = base_layers(
        httpx2.Client(transport=httpx2.MockTransport(handle)), "ghcr.io/linuxserver/baseimage-ubuntu:noble", None
    )
    assert base["platforms"] == {"amd64": {"digest": None, "layers": ["sha256:1", "sha256:2"]}}


def test_parse_reference() -> None:
    assert parse_reference("ghcr.io/linuxserver/baseimage-alpine:3.24") == (
        "ghcr.io",
        "linuxserver/baseimage-alpine",
        "3.24",
    )
    assert parse_reference("linuxserver/baseimage-alpine") == ("ghcr.io", "linuxserver/baseimage-alpine", "latest")
    assert parse_reference("localhost:5000/x/y:1") == ("localhost:5000", "x/y", "1")
    assert parse_reference("ghcr.io/a/b@sha256:abc") == ("ghcr.io", "a/b", "sha256:abc")


def test_refresh_bases_fetches_once_and_survives_registry_errors() -> None:
    store = build_store()
    assert list(store.bases) == [BASE_DIGEST]  # multidb's base answers 404 and is left for the next run
    assert store.bases[BASE_DIGEST]["fetched_at"] == NOW
    assert store.bases[BASE_DIGEST]["platforms"]["arm64"]["layers"] == [layer_digest(0)]
    assert refresh_bases(store, registry_http(), now=lambda: NOW) == []
    store.bases.clear()
    assert refresh_bases(store, registry_http(), now=lambda: NOW) == [BASE_DIGEST]
