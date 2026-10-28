"""
The shared fixture: a store built by running the real ingest against a fake GitHub that serves three
images (sonarr with two live branches, swag, and a constructed multi-arch image with an external database),
releases with constructed bundles, syft documents, layer lists, test reports and report tarballs, then the
observer. The newest builds carry the counts of the scan their build made of itself (a fake grype that answers from
`fixtures/grype.json`, as `builder record` would have stored it in record.json).
"""

from __future__ import annotations

import copy
import gzip
import hashlib
import io
import json
import tarfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx2
import pytest
import yaml
from builder.derive.vulns import compact, summary_of
from fastapi.testclient import TestClient

from lsio_hub import mods as mods_module
from lsio_hub import prootapps
from lsio_hub.app import create_app
from lsio_hub.build import render
from lsio_hub.config import SiteConfig
from lsio_hub.fleet import Fleet, hub_settings, load_fleet
from lsio_hub.generate.common import GenerateContext, make_context
from lsio_hub.ingest import reconcile
from lsio_hub.observe import observe
from lsio_hub.sources.github import FileKey, GitHub
from lsio_hub.store import Store, load_store, save_store

FIXTURES = Path(__file__).parent / "fixtures"
NOW = "2026-10-24T12:00:00.000Z"
ASSETS = "https://assets.test"
ORG = "linuxserver-playground"
Json = dict[str, Any]


def load_manifest(name: str) -> Json:
    data: Json = yaml.safe_load((FIXTURES / "manifests" / f"{name}.yml").read_text())
    for entry in data.get("changelog", []):
        entry["date"] = str(entry["date"])
    return data


MANIFESTS = {
    ("docker-sonarr", "master"): load_manifest("sonarr.master"),
    ("docker-sonarr", "develop"): load_manifest("sonarr.develop"),
    ("docker-swag", "master"): load_manifest("swag.master"),
    ("docker-multidb", "master"): load_manifest("multidb.master"),
}


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


# ---------------------------------------------------------------------------------------------------
# Bundle construction


def syft_document(packages: list[tuple[str, str, str]]) -> Json:
    """A minimal syft JSON with (name, version, type) artifacts."""
    return {
        "artifacts": [
            {
                "id": _sha(f"{n}{v}{t}")[:16],
                "name": n,
                "version": v,
                "type": t,
                "purl": f"pkg:{'apk' if t == 'apk' else t}/{n}@{v}",
                "licenses": [{"value": "MIT", "spdxExpression": "MIT"}] if t == "apk" else ["GPL-3.0"],
            }
            for n, v, t in packages
        ],
        "source": {"type": "image"},
        "schema": {"version": "16.0.0"},
    }


LAYER_INSTRUCTIONS = ("COPY /root-out/ /", "RUN /bin/sh -c apk add curl", "COPY root/ / # buildkit")
"""created_by per fixture layer: the base's rootfs, then the Dockerfile's RUN and COPY as BuildKit records them."""
BASE_DIGEST = "sha256:" + "b" * 64
"""The base index digest most fixture builds record; the registry fixture serves its manifests."""
UNKNOWN_BASE_DIGEST = "sha256:" + "e" * 64
"""multidb's base digest; the registry fixture answers 404 for it, so the harness's flags stand."""
DOCKERFILE = "FROM ghcr.io/linuxserver/baseimage-alpine:3.24\nRUN apk add curl\nCOPY root/ /\n"


def layer_digest(i: int) -> str:
    return "sha256:" + _sha(f"layer{i}")


def layers_document(count: int = 3) -> list[Json]:
    return [
        {
            "index": i,
            "digest": layer_digest(i),
            "size": 1000 * (i + 1),
            "created_by": LAYER_INSTRUCTIONS[i] if i < len(LAYER_INSTRUCTIONS) else f"RUN step {i}",
            "from_base": i == 0,
        }
        for i in range(count)
    ]


def make_report(image: str, tag: str, arch: str, *, success: bool = True) -> Json:
    return {
        "schema": 1,
        "image": image,
        "tag": f"{'amd64' if arch == 'amd64' else 'arm64v8'}-{tag}",
        "arch": arch,
        "started": "2026-10-20T12:00:00Z",
        "finished": "2026-10-20T12:03:00Z",
        "success": success,
        "runner": "ubuntu-24.04" if arch == "amd64" else "ubuntu-24.04-arm",
        "tests": [
            {"name": "Container startup", "status": "PASS", "seconds": 4.2},
            {"name": "Get package info", "status": "PASS", "seconds": 1.0},
            {
                "name": "Take screenshot",
                "status": "PASS" if success else "FAIL",
                "message": "" if success else "timeout",
                "seconds": 9.5,
            },
        ],
        "warnings": {} if success else {"dotnet": "Dotnet runtime check warned"},
        "startup_seconds": 4.2,
        "files": {
            "html": "report/index.html",
            "container_log": "report/container.log",
            "screenshot": "report/screenshot.png",
            "sysinfo": "report/sysinfo.txt",
        },
        "runtime": {"rss_bytes": 120_000_000, "pids": 7, "listening_tcp": [8989], "s6_services": ["svc-sonarr"]},
    }


PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d4944415478da6364f8cfc000000401010007ac3ec30000000049454e44ae426082"
)


def report_tarball(image: str, arch: str) -> bytes:
    """A test.<arch>.tar.gz with the files the report names, one extra file, and one unsafe path to ignore."""
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        files = {
            "report/index.html": f"<html><body><h1>{image} {arch} report</h1></body></html>".encode(),
            "report/container.log": b"[ls.io-init] done.\n",
            "report/screenshot.png": PNG,
            "report/sysinfo.txt": b"Linux\n",
            "report/package_diff.txt": b"+curl 8.0\n",
            "../escape.txt": b"nope",
        }
        for name, content in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(content)
            tar.addfile(info, io.BytesIO(content))
    return buffer.getvalue()


def bundle(
    image: str,
    branch: str,
    upstream: str,
    ls_build: int,
    created: str,
    *,
    release_tag: str = "latest",
    base_digest: str = "b" * 64,
    dockerfile: str = DOCKERFILE,
    arm64_result: str = "success",
    reason: str = "upstream",
    test_enabled: bool = True,
    env: list[str] | None = None,
) -> Json:
    prefix = "" if release_tag == "latest" else f"{release_tag}-"
    tag = f"{prefix}{upstream}-ls{ls_build}"
    assets = ["build.json"]
    for arch in ("amd64", "arm64"):
        assets += [
            f"packages.{arch}.json.gz",
            f"layers.{arch}.json",
            f"test.{arch}.json",
            f"test.{arch}.tar.gz",
            f"files.{arch}.json.gz",
        ]
    platforms: list[Json] = [
        {
            "arch": "amd64",
            "result": "success",
            "digest": "sha256:" + _sha(f"{tag}amd64"),
            "size": 50_000_000 + ls_build * 1000,
            "layers": 3,
        }
    ]
    if arm64_result == "success":
        platforms.append(
            {
                "arch": "arm64",
                "result": "success",
                "digest": "sha256:" + _sha(f"{tag}arm64"),
                "size": 48_000_000 + ls_build * 1000,
                "layers": 3,
            }
        )
    else:
        platforms.append({"arch": "arm64", "result": arm64_result})
    return {
        "schema": 1,
        "image": image,
        "repository": f"{ORG}/docker-{image}",
        "branch": branch,
        "mode": "live",
        "version": {
            "upstream": upstream,
            "upstream_clean": upstream,
            "semver": ".".join(upstream.split(".")[:3]) if upstream.count(".") >= 2 else None,
            "ls_build": ls_build,
            "tag": tag,
            "release_tag": release_tag,
            "tags": [release_tag, tag],
            "source": "json",
        },
        "commit": _sha(f"{image}{tag}")[:40],
        "created": created,
        "reason": reason,
        "base": {
            "family": "alpine",
            "image": "ghcr.io/linuxserver/baseimage-alpine:3.24",
            "digest": "sha256:" + base_digest,
        },
        "platforms": platforms,
        "labels": {"org.opencontainers.image.version": tag},
        "config": {
            "env": env or ["PATH=/usr/bin", "HOME=/root"],
            "exposed_ports": ["8989/tcp"],
            "volumes": ["/config"],
        },
        "dockerfile": {"amd64": dockerfile, "arm64": dockerfile.replace("alpine:", "alpine:arm64v8-")},
        "packages": {"amd64": {"count": 3, "distro": "Alpine Linux v3.24", "hash": "abcd1234"}},
        "test": {
            "enabled": test_enabled,
            "success": test_enabled and arm64_result == "success",
            "per_arch": {"amd64": True, "arm64": arm64_result == "success"},
        },
        "notes": {
            "linuxserver": "* Add krb5-libs",
            "upstream": "Upstream fixed things",
            "upstream_url": "https://example.org/notes",
        },
        "assets": [{"name": a, "size": 10, "sha256": "d" * 64, "url": f"{ASSETS}/{image}/{tag}/{a}"} for a in assets],
        "workflow": {
            "run_id": 1000 + ls_build,
            "run_url": f"https://github.com/{ORG}/docker-{image}/actions/runs/{1000 + ls_build}",
            "workflows_ref": "v1",
        },
    }


PACKAGES = {
    "sonarr@4.0.19.2000-ls1": [
        ("curl", "8.9.0-r0", "apk"),
        ("sqlite-libs", "3.46.0-r0", "apk"),
        ("Sonarr", "4.0.19.2000", "dotnet"),
    ],
    "sonarr@4.0.20.3014-ls2": [
        ("curl", "8.9.1-r0", "apk"),
        ("sqlite-libs", "3.46.0-r0", "apk"),
        ("Sonarr", "4.0.20.3014", "dotnet"),
        ("krb5-libs", "1.21.3-r0", "apk"),
    ],
    "sonarr@develop-5.0.1.1234-ls1": [("curl", "8.9.1-r0", "apk"), ("Sonarr", "5.0.1.1234", "dotnet")],
    "swag@5.2.0-ls1": [("curl", "8.9.1-r0", "apk"), ("nginx", "1.28.0-r0", "apk"), ("certbot", "5.2.0", "python")],
    "multidb@1.0.0-ls1": [("curl", "8.9.1-r0", "apk"), ("libdrm", "2.4.120-r0", "apk")],
    "multidb@1.0.0-ls2": [("curl", "8.9.0-r0", "apk"), ("libdrm", "2.4.121-r0", "apk")],
}

SONARR_LS1 = bundle("sonarr", "master", "4.0.19.2000", 1, "2026-10-01T10:00:00Z")
SONARR_LS2 = bundle("sonarr", "master", "4.0.20.3014", 2, "2026-10-20T19:16:08Z")
SONARR_DEV = bundle("sonarr", "develop", "5.0.1.1234", 1, "2026-10-21T08:00:00Z", release_tag="develop")
SWAG_LS1 = bundle("swag", "master", "5.2.0", 1, "2026-10-22T06:00:00Z", test_enabled=False)
MULTIDB_LS1 = bundle(
    "multidb", "master", "1.0.0", 1, "2026-10-10T00:00:00Z", arm64_result="failure", base_digest="e" * 64
)
MULTIDB_LS2 = bundle(
    "multidb",
    "master",
    "1.0.0",
    2,
    "2026-10-23T00:00:00Z",
    base_digest="e" * 64,
    dockerfile=DOCKERFILE.replace("apk add curl", "apk add curl jq"),
    reason="push",
    env=["PATH=/usr/bin", "HOME=/root", "NEW_VAR=1"],
)
BUNDLES = [SONARR_LS1, SONARR_LS2, SONARR_DEV, SWAG_LS1, MULTIDB_LS1, MULTIDB_LS2]
BAD_BUNDLE = {**copy.deepcopy(MULTIDB_LS1), "version": {**MULTIDB_LS1["version"], "tag": "bad-ls9"}, "platforms": []}


def release_for(b: Json, *, html: bool = True) -> Json:
    tag = b["version"]["tag"]
    return {
        "tag_name": tag,
        "target_commitish": b["branch"],
        "draft": False,
        "prerelease": b["version"]["release_tag"] != "latest",
        "created_at": b["created"],
        "html_url": f"https://github.com/{b['repository']}/releases/tag/{tag}",
        "assets": [
            {"name": a["name"], "url": a["url"], "browser_download_url": a["url"], "size": 10} for a in b["assets"]
        ],
    }


RELEASES: dict[str, list[Json]] = {
    "docker-sonarr": [release_for(SONARR_DEV), release_for(SONARR_LS2), release_for(SONARR_LS1)],
    "docker-swag": [release_for(SWAG_LS1)],
    "docker-multidb": [
        release_for(MULTIDB_LS2),
        release_for(BAD_BUNDLE),
        release_for(MULTIDB_LS1),
        {**release_for(MULTIDB_LS1), "tag_name": "feature-ls1", "target_commitish": "feature"},
    ],
}


def asset_bytes(url: str) -> bytes | None:
    """What the fake GitHub serves for an asset URL."""
    if not url.startswith(ASSETS + "/"):
        return None
    image, tag, name = url[len(ASSETS) + 1 :].split("/", 2)
    if name == "build.json":
        b = next((b for b in [*BUNDLES, BAD_BUNDLE] if b["image"] == image and b["version"]["tag"] == tag), None)
        return json.dumps(b).encode() if b else None
    arch = name.split(".")[1]
    if name.startswith("packages."):
        return gzip.compress(json.dumps(syft_document(PACKAGES.get(f"{image}@{tag}", []))).encode())
    if name.startswith("layers."):
        return json.dumps(layers_document()).encode()
    if name.startswith("test.") and name.endswith(".json"):
        return json.dumps(make_report(image, tag, arch, success=not (image == "multidb" and arch == "arm64"))).encode()
    if name.startswith("test.") and name.endswith(".tar.gz"):
        return report_tarball(image, arch)
    if name.startswith("files."):
        return gzip.compress(json.dumps([{"path": "/usr/bin/curl", "layer": 1, "type": "file"}]).encode())
    return None


MOD_YMLS: dict[str, Json] = yaml.safe_load((FIXTURES / "mods.yml").read_text())
"""The mod.yml of each fixture docker-mods branch."""
PROOT_METADATA = """include:
  - name: firefox
    full_name: Firefox
    arch: linux/amd64,linux/arm64
    category: Network
    icon: firefox.svg
    description: "Firefox Browser."
  - name: anydesk
    full_name: AnyDesk 
    arch: linux/amd64
    category: Network
    icon: anydesk.svg
    description: "AnyDesk remote desktop."
  - name: steam
    full_name: Steam
    arch: linux/amd64
    category: Game
    icon: steam.svg
    description: "Steam."
    disabled: True
"""
"""proot-apps' metadata/metadata.yml: two apps (out of title order) and a disabled one."""
PROOT_RELEASES = [
    {"tag_name": "prerelease-abc", "prerelease": True, "html_url": "https://github.test/pre", "created_at": NOW},
    {"tag_name": "0.5.5", "prerelease": False, "html_url": "https://github.test/0.5.5", "published_at": NOW},
]


# ---------------------------------------------------------------------------------------------------
# Fake GitHub


class FakeGitHub(GitHub):
    """Answers the calls ingest, observe and mods make, from the fixtures above."""

    def __init__(self) -> None:
        super().__init__(registry_http(), "token")  # the registry fixture, for the base image manifests
        self.downloads: list[str] = []
        self.listings = 0
        self.batched = 0

    def org_repos(self, org: str) -> list[Json]:
        repos = sorted({repo for repo, _ in MANIFESTS})
        return [
            {
                "name": r,
                "url": f"https://github.com/{ORG}/{r}",
                "stars": 7 if r == "docker-sonarr" else 0,
                "pushed_at": "2026-10-23T00:00:00Z",
                "archived": r == "docker-multidb",
                "default_branch": "master",
                "branches": sorted(ref for name, ref in MANIFESTS if name == r),
            }
            for r in repos
        ] + [
            {
                "name": "builder",
                "url": f"https://github.com/{ORG}/builder",
                "stars": 1,
                "pushed_at": None,
                "archived": False,
                "default_branch": "main",
            }
        ]

    def file_text(self, repo: str, path: str, ref: str) -> str | None:
        repo_name = repo.split("/")[1]
        if path == "image.yml" and (repo_name, ref) in MANIFESTS:
            return yaml.safe_dump(MANIFESTS[(repo_name, ref)], sort_keys=False)
        if repo_name == "docker-mods" and path == "mod.yml" and ref in MOD_YMLS:
            return yaml.safe_dump(MOD_YMLS[ref], sort_keys=False)
        if repo_name == "proot-apps" and path == "metadata/metadata.yml" and ref == "master":
            return PROOT_METADATA
        return None

    def releases(self, repo: str, *, max_pages: int = 3) -> list[Json]:
        if repo == f"{ORG}/proot-apps":
            return list(PROOT_RELEASES)
        return list(RELEASES.get(repo.split("/")[1], []))

    def org_releases(self, org: str, *, per_repo: int = 30) -> dict[str, list[Json]]:
        """What the GraphQL listing returns: the REST listing without assets."""
        self.listings += 1
        return {
            repo["name"]: [
                {k: r[k] for k in ("tag_name", "created_at", "html_url", "draft")}
                for r in self.releases(f"{org}/{repo['name']}")[:per_repo]
            ]
            for repo in self.org_repos(org)
        }

    def file_texts(self, files: list[FileKey], *, batch: int = 25, workers: int = 8) -> dict[FileKey, str | None]:
        """The GraphQL batch read; a file that fails is left out, as a truncated one would be."""
        texts: dict[FileKey, str | None] = {}
        for repo, ref, path in files:
            try:
                texts[(repo, ref, path)] = self.file_text(repo, path, ref)
            except Exception:
                continue
        self.batched += len(texts)
        return texts

    def release_by_tag(self, repo: str, tag: str) -> Json:
        for release in self.releases(repo):
            if release["tag_name"] == tag:
                return release
        raise httpx2.HTTPStatusError("404", request=httpx2.Request("GET", repo), response=httpx2.Response(404))

    def get(self, path: str, **params: Any) -> Any:
        if path.startswith("repos/") and path.count("/") == 2:
            return {"default_branch": "master"}
        raise AssertionError(f"unexpected GET {path}")

    def paginate(self, path: str, *, per_page: int = 100, max_pages: int = 10, **params: Any) -> list[Json]:
        if path.endswith("docker-mods/branches"):
            return [{"name": b} for b in ["master", "template", *MOD_YMLS]]
        if path.endswith("/branches"):
            repo_name = path.split("/")[2]
            return [{"name": ref} for name, ref in MANIFESTS if name == repo_name]
        raise AssertionError(f"unexpected paginate {path}")

    def download(self, url: str) -> bytes:
        self.downloads.append(url)
        data = asset_bytes(url)
        if data is None:
            raise httpx2.HTTPStatusError("404", request=httpx2.Request("GET", url), response=httpx2.Response(404))
        return data


BASE_MANIFESTS: dict[str, Json] = {
    BASE_DIGEST: {
        "mediaType": "application/vnd.oci.image.index.v1+json",
        "manifests": [
            {"digest": "sha256:" + _sha("base-amd64"), "platform": {"architecture": "amd64", "os": "linux"}},
            {"digest": "sha256:" + _sha("base-attestation"), "platform": {"architecture": "unknown", "os": "unknown"}},
            {"digest": "sha256:" + _sha("base-arm64"), "platform": {"architecture": "arm64", "os": "linux"}},
        ],
    },
    "sha256:" + _sha("base-amd64"): {
        "mediaType": "application/vnd.oci.image.manifest.v1+json",
        "layers": [{"digest": layer_digest(0), "size": 1000}],
    },
    "sha256:" + _sha("base-arm64"): {
        "mediaType": "application/vnd.oci.image.manifest.v1+json",
        "layers": [{"digest": layer_digest(0), "size": 1000}],
    },
}
"""What the registry fixture serves for ghcr.io/linuxserver/baseimage-alpine: one base layer, the fixture's layer 0."""


def registry_http() -> httpx2.Client:
    """An HTTP client serving GHCR tag lists and the base image manifests."""

    def handle(request: httpx2.Request) -> httpx2.Response:
        if request.url.path == "/token":
            return httpx2.Response(200, json={"token": "anon"})
        if request.url.path.startswith("/v2/linuxserver/baseimage-alpine/manifests/"):
            manifest = BASE_MANIFESTS.get(request.url.path.rsplit("/", 1)[1])
            return httpx2.Response(200, json=manifest) if manifest else httpx2.Response(404)
        if request.url.path.endswith("/tags/list"):
            name = request.url.path.split("/")[3]
            return (
                httpx2.Response(404)
                if name == "multidb"
                else httpx2.Response(200, json={"tags": ["latest", "amd64-latest", "4.0.20.3014-ls2"]})
            )
        return httpx2.Response(404)

    return httpx2.Client(transport=httpx2.MockTransport(handle))


GRYPE_REPORT: Json = json.loads((FIXTURES / "grype.json").read_text())
"""A trimmed real grype report (sonarr 4.0.20.3014-ls1, amd64): dotnet fixes, Alpine findings with none, a wont-fix."""
DB_DATE = "2026-10-24T17:45:29Z"


class FakeGrype:
    """Answers like grype 0.121.0 would, from the fixture; arm64 scans lack the last (deb, wont-fix) finding."""

    def __init__(self, *, version: str | None = "0.121.0", db_date: str | None = DB_DATE) -> None:
        self._version = version
        self._db_date = db_date
        self.scans: list[str] = []
        self.updates = 0

    def version(self) -> str | None:
        return self._version

    def db_date(self, *, update: bool) -> str | None:
        self.updates += int(update)
        return self._db_date

    def scan(self, sbom: Path) -> Json:
        self.scans.append(sbom.name)
        report = copy.deepcopy(GRYPE_REPORT)
        report["descriptor"]["db"]["status"]["built"] = self._db_date
        if "arm64" in sbom.name:
            report["matches"] = [m for m in report["matches"] if m["artifact"]["type"] != "deb"]
        return report


SCANNED = {"sonarr": ["4.0.20.3014-ls2", "develop-5.0.1.1234-ls1"], "swag": ["5.2.0-ls1"], "multidb": ["1.0.0-ls2"]}
"""The builds whose record.json held a scan; the others (older releases) have none."""


def own_scans(grype: FakeGrype | None = None) -> dict[str, Json]:
    """A build's scans per architecture, as `builder record` writes them into record.json `vulns`."""
    grype = grype or FakeGrype()
    return {
        arch: compact(grype.scan(Path(f"packages.{arch}.json")), DB_DATE, "2026-10-20T19:30:00Z")
        for arch in ("amd64", "arm64")
    }


def build_store(github: FakeGitHub | None = None) -> Store:
    github = github or FakeGitHub()
    store = Store()
    now = lambda: NOW  # noqa: E731
    reconcile(store, github, now=now)
    http = registry_http()
    observe(store, github, http, now=now)
    mods_module.refresh_mods(store, github, now=now)
    prootapps.refresh_proot_apps(store, github, now=now)
    for name, tags in SCANNED.items():
        for tag in tags:
            store.images[name].vulns[tag] = summary_of(own_scans())
    return store


@pytest.fixture(scope="session")
def session_store(tmp_path_factory: pytest.TempPathFactory) -> Store:
    """Built once, then round-tripped through data/ so every test sees what a checkout would."""
    directory = tmp_path_factory.mktemp("data")
    save_store(directory, build_store())
    return load_store(directory)


@pytest.fixture
def store(session_store: Store) -> Store:
    return copy.deepcopy(session_store)


@pytest.fixture
def config() -> SiteConfig:
    return SiteConfig(site_url="https://example.github.io", base_path="/hub/")


@pytest.fixture
def fleet(store: Store, config: SiteConfig) -> Fleet:
    return load_fleet(store, config)


@pytest.fixture
def gen(store: Store, config: SiteConfig) -> GenerateContext:
    return make_context(store, config, hub_settings(config))


@pytest.fixture
def files(fleet: Fleet, config: SiteConfig) -> dict[str, bytes]:
    """Every file of the built site."""
    return render(fleet, config)


@pytest.fixture
def spec(files: dict[str, bytes]) -> dict[str, Any]:
    parsed: dict[str, Any] = json.loads(files["openapi.json"])
    return parsed


@pytest.fixture
def client(fleet: Fleet, config: SiteConfig) -> Iterator[TestClient]:
    with TestClient(create_app(fleet, config)) as c:
        yield c


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("lsio_hub.sources.http.time.sleep", lambda _: None)
