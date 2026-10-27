"""The observer, the mods fetcher and the registry client."""

import json

import httpx2
import pytest

from lsio_hub import mods
from lsio_hub.ingest import refresh_bases
from lsio_hub.models import Mod
from lsio_hub.observe import observe
from lsio_hub.sources.github import GitHub
from lsio_hub.sources.registry import GhcrPackage, base_layers, ghcr_tags, parse_reference
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
    assert by_branch["universal-docker"]["upstream"] == {
        "url": "https://www.docker.com/",
        "type": "combined",
        "source": "github_release moby/moby + github_release docker/compose",
    }
    assert git["upstream"] is None
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
    assert parse_reference("docker.io/alpine:3.24") == ("registry-1.docker.io", "library/alpine", "3.24")
    assert parse_reference("alpine") == ("registry-1.docker.io", "library/alpine", "latest")
    hub = "registry-1.docker.io"
    assert parse_reference("docker.io/linuxserver/x@sha256:abc") == (hub, "linuxserver/x", "sha256:abc")


def test_base_layers_from_docker_hub() -> None:
    """Docker Hub's tokens come from auth.docker.io for registry.docker.io; its API is on registry-1."""
    hosts: list[str] = []

    def handle(request: httpx2.Request) -> httpx2.Response:
        hosts.append(request.url.host)
        if request.url.host == "auth.docker.io":
            assert request.url.params["service"] == "registry.docker.io"
            assert request.url.params["scope"] == "repository:library/alpine:pull"
            return httpx2.Response(200, json={"token": "hub"})
        assert request.headers["authorization"] == "Bearer hub"
        assert request.url.path == "/v2/library/alpine/manifests/sha256:abc"
        return httpx2.Response(200, json={"config": {}, "layers": [{"digest": "sha256:1"}]})

    base = base_layers(httpx2.Client(transport=httpx2.MockTransport(handle)), "docker.io/alpine:3.24", "sha256:abc")
    assert base["platforms"] == {"amd64": {"digest": "sha256:abc", "layers": ["sha256:1"]}}
    assert hosts == ["auth.docker.io", "registry-1.docker.io"]


def test_refresh_bases_fetches_once_and_survives_registry_errors() -> None:
    store = build_store()
    assert list(store.bases) == [BASE_DIGEST]  # multidb's base answers 404 and is left for the next run
    assert store.bases[BASE_DIGEST]["fetched_at"] == NOW
    assert store.bases[BASE_DIGEST]["platforms"]["arm64"]["layers"] == [layer_digest(0)]
    assert refresh_bases(store, registry_http(), now=lambda: NOW) == []
    store.bases.clear()
    assert refresh_bases(store, registry_http(), now=lambda: NOW) == [BASE_DIGEST]


def test_a_failed_base_lookup_waits_a_day() -> None:
    store = build_store()
    unknown = UNKNOWN_BASE_DIGEST
    assert store.status["bases"][unknown]["checked_at"] == NOW and "404" in store.status["bases"][unknown]["error"]
    requests: list[str] = []

    def counting() -> httpx2.Client:
        inner = registry_http()

        def handle(request: httpx2.Request) -> httpx2.Response:
            requests.append(request.url.path)
            return inner.request(request.method, request.url, headers=request.headers)

        return httpx2.Client(transport=httpx2.MockTransport(handle))

    assert refresh_bases(store, counting(), now=lambda: "2026-10-25T11:00:00.000Z") == []
    assert requests == []  # 23 hours later: not yet
    assert refresh_bases(store, counting(), now=lambda: "2026-10-25T12:00:01.000Z") == []
    assert any(unknown in path for path in requests)  # a day later it is tried again, and fails again
    assert store.status["bases"][unknown]["checked_at"] == "2026-10-25T12:00:01.000Z"


def test_org_releases_reads_every_page_and_drops_drafts() -> None:
    pages = [
        {
            "pageInfo": {"hasNextPage": True, "endCursor": "c1"},
            "nodes": [
                {
                    "name": "docker-sonarr",
                    "releases": {
                        "nodes": [
                            {"tagName": "2-ls2", "createdAt": "2026-10-26T13:00:00Z", "url": "u2", "isDraft": True},
                            {"tagName": "1-ls1", "createdAt": "2026-10-25T13:00:00Z", "url": "u1", "isDraft": False},
                        ]
                    },
                }
            ],
        },
        {"pageInfo": {"hasNextPage": False}, "nodes": [{"name": "builder", "releases": {"nodes": []}}]},
    ]
    variables: list[Json] = []

    def handle(request: httpx2.Request) -> httpx2.Response:
        body = json.loads(request.content)
        variables.append(body["variables"])
        page = pages[len(variables) - 1]
        return httpx2.Response(200, json={"data": {"organization": {"repositories": page}}})

    gh = GitHub(httpx2.Client(transport=httpx2.MockTransport(handle)), "t")
    assert gh.org_releases("linuxserver-playground", per_repo=5) == {
        "docker-sonarr": [
            {"tag_name": "1-ls1", "created_at": "2026-10-25T13:00:00Z", "html_url": "u1", "draft": False}
        ],
        "builder": [],
    }
    assert [v["cursor"] for v in variables] == [None, "c1"] and variables[0]["releases"] == 5


GOLANG: Json = {
    "schema": 1,
    "name": "golang",
    "target": "code-server",
    "summary": "Adds golang to code-server.",
    "maintainers": ["x"],
    "platforms": ["amd64"],
    "upstream": {
        "version": {"type": "json", "url": "https://go.dev/dl/?mode=json", "jq": ".[0].version"},
        "tags": ["major", "minor"],
        "lines": [
            {"name": "previous", "version": {"type": "json", "url": "u", "jq": ".[1].version"}, "tags": ["minor"]},
            {"name": "unstable", "version": {"type": "json", "url": "u", "jq": "rc"}},
        ],
    },
}
# What the mods package holds: tag -> (version label, revision, created). Aliases share their build's image.
MOD_IMAGES: dict[str, tuple[str | None, str, str]] = {
    "code-server-golang": ("1.27.3", "92906ee" + "0" * 33, "2026-10-27T16:39:50Z"),
    "code-server-golang-1.26.10": ("1.26.10", "aaaaaaa" + "0" * 33, "2026-10-27T18:00:00Z"),
    "universal-git": (None, "4f30cbe" + "0" * 33, "2026-10-25T17:53:53Z"),
}
MOD_TAGS = [
    "code-server-golang",
    "code-server-golang-1",
    "code-server-golang-1.27",
    "code-server-golang-1.27.3",
    "code-server-golang-1.27.3-92906ee",
    "code-server-golang-92906ee",
    "code-server-golang-1.26",
    "code-server-golang-1.26.10",
    "universal-git",
    "universal-git-4f30cbe",
]


def mods_registry(requests: list[str], *, tags_status: int = 200) -> GhcrPackage:
    def handle(request: httpx2.Request) -> httpx2.Response:
        path = request.url.path
        if path == "/token":
            return httpx2.Response(200, json={"token": "anon"})
        requests.append(path)
        if path.endswith("/tags/list"):
            return httpx2.Response(tags_status, json={"tags": MOD_TAGS})
        if "/manifests/" in path:
            tag = path.rsplit("/", 1)[1]
            if tag not in MOD_IMAGES:
                return httpx2.Response(404)
            return httpx2.Response(
                200,
                json={"config": {"digest": f"sha256:c-{tag}"}, "layers": []},
                headers={"docker-content-digest": f"sha256:d-{tag}"},
            )
        if "/blobs/sha256:c-" in path:
            version, revision, created = MOD_IMAGES[path.rsplit("sha256:c-", 1)[1]]
            labels = {"org.opencontainers.image.revision": revision}
            if version:
                labels["org.opencontainers.image.version"] = version
            return httpx2.Response(200, json={"created": created, "config": {"Labels": labels}})
        return httpx2.Response(404)

    return GhcrPackage(httpx2.Client(transport=httpx2.MockTransport(handle)), "mods")


def resolved(versions: dict[str, str]) -> mods.Resolver:
    return lambda source, platforms: versions[source["jq"]]


def test_mod_builds_per_version_line() -> None:
    requests: list[str] = []
    package = mods_registry(requests)
    entry = mods.from_manifest(GOLANG, "code-server-golang")
    tags = set(package.tags())
    resolve = resolved({".[1].version": "1.26.10", "rc": "1.28rc1"})
    builds = mods.mod_builds(entry, GOLANG, package, tags, [], resolve)
    image = "ghcr.io/linuxserver-playground/mods"
    assert builds == [
        {
            "line": None,
            "version": "1.27.3",
            "built_at": "2026-10-27T16:39:50Z",
            "pin": f"{image}:code-server-golang-1.27.3",
            "tags": [
                f"{image}:code-server-golang",
                f"{image}:code-server-golang-1",
                f"{image}:code-server-golang-1.27",
            ],
            "digest": "sha256:d-code-server-golang",
            "revision": "92906ee" + "0" * 33,
        },
        {
            "line": "previous",
            "version": "1.26.10",
            "built_at": "2026-10-27T18:00:00Z",
            "pin": f"{image}:code-server-golang-1.26.10",
            "tags": [f"{image}:code-server-golang-1.26"],
            "digest": "sha256:d-code-server-golang-1.26.10",
            "revision": "aaaaaaa" + "0" * 33,
        },
    ]  # unstable resolved to 1.28rc1, which is not built yet and was never seen: no entry
    # An unchanged digest is one request per line; a line whose new version is not built keeps its last build; a
    # line that resolves to an earlier line's version is the earlier line's.
    requests.clear()
    unstable = {**builds[1], "line": "unstable", "version": "1.27rc3", "pin": f"{image}:code-server-golang-1.27rc3"}
    again = mods.mod_builds(entry, GOLANG, package, tags, [*builds, unstable], resolve)
    assert again == [*builds, unstable] and len(requests) == 2
    same = resolved({".[1].version": "1.27.3", "rc": "1.28rc1"})
    assert [b["line"] for b in mods.mod_builds(entry, GOLANG, package, tags, builds, same)] == [None]
    # Without the resolver the other lines keep what the previous refresh found.
    assert mods.mod_builds(entry, GOLANG, package, tags, builds, None) == builds


def test_refresh_mods_reads_the_mods_package() -> None:
    requests: list[str] = []
    store = Store()
    mods.refresh_mods(store, FakeGitHub(), now=lambda: NOW, package=mods_registry(requests))
    by_branch = {m["branch"]: m for m in store.mods["mods"]}
    git = by_branch["universal-git"]["builds"]
    assert git == [
        {
            "line": None,
            "version": None,
            "built_at": "2026-10-25T17:53:53Z",
            "pin": "ghcr.io/linuxserver-playground/mods:universal-git-4f30cbe",
            "tags": ["ghcr.io/linuxserver-playground/mods:universal-git"],
            "digest": "sha256:d-universal-git",
            "revision": "4f30cbe" + "0" * 33,
        }
    ]
    assert by_branch["universal-docker"]["builds"] == []  # never published
    Mod.model_validate(by_branch["universal-git"])

    # The registry down: every mod keeps its builds, and the status says why.
    mods.refresh_mods(store, FakeGitHub(), now=lambda: NOW, package=mods_registry([], tags_status=403))
    assert {m["branch"]: m for m in store.mods["mods"]}["universal-git"]["builds"] == git
    assert "GHCR tags of the mods package" in store.status["sources"]["mods"]["error"]
    assert store.status["sources"]["mods"]["ok"] is True
    # A run without the registry (tests, local runs) keeps them too.
    mods.refresh_mods(store, FakeGitHub(), now=lambda: NOW)
    assert {m["branch"]: m for m in store.mods["mods"]}["universal-git"]["builds"] == git
