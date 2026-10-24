"""The observer, the mods fetcher and the registry client."""

import httpx2

from lsio_hub import mods
from lsio_hub.observe import observe
from lsio_hub.sources.registry import ghcr_tags
from lsio_hub.store import Store

from .conftest import NOW, FakeGitHub, build_store, legacy_http


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
    observe(store, Broken(), legacy_http(), now=lambda: "2026-10-25T00:00:00Z")
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


def test_legacy_mod_list_conversion() -> None:
    store = build_store()
    by_branch = {m["branch"]: m for m in store.mods["mods"]}
    docker = by_branch["universal-docker"]
    assert docker["name"] == "docker" and docker["target"] == "universal"
    assert docker["applies_to"] == ["universal", "code-server", "openvscode-server", "vscodium-web"]
    poetry = by_branch["code-server-python3-poetry"]
    assert poetry["name"] == "python3-poetry" and poetry["target"] == "code-server"
    assert set(poetry["applies_to"]) == {"code-server", "openvscode-server", "vscodium-web"}
    assert by_branch["radarr-striptracks"]["applies_to"] == ["radarr", "sonarr"]
    assert by_branch["swag-auto-reload"]["applies_to"] == ["swag", "nginx"]


def test_playground_mods_when_the_repository_exists() -> None:
    store = Store()
    mods.refresh_mods(store, FakeGitHub(mods_repo=True), legacy_http(), now=lambda: NOW)
    assert store.mods["source"].startswith("mod.yml on each branch")
    [mod] = store.mods["mods"]
    assert mod["name"] == "git" and mod["image"] == "ghcr.io/linuxserver-playground/mods:universal-git"
    assert mod["env"] == [{"name": "GIT_USER", "description": "Commit author", "default": "abc", "required": False}]
    assert mod["platforms"] == ["amd64", "arm64"] and mod["applies_to"] == ["universal"]


def test_mods_failure_keeps_previous() -> None:
    def handle(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(500)

    store = build_store()
    http = httpx2.Client(transport=httpx2.MockTransport(handle))
    mods.refresh_mods(store, FakeGitHub(), http, now=lambda: "2026-10-25T00:00:00Z")
    assert len(store.mods["mods"]) == 88
    assert store.status["sources"]["mods"]["ok"] is False and store.status["sources"]["mods"]["fetched_at"] == NOW
