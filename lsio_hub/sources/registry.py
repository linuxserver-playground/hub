"""
Registries, read anonymously: the tag list of a public GHCR package and the layer digests of a base image on
GHCR or Docker Hub. Both hand out a pull token without credentials; nothing here needs GITHUB_TOKEN.
"""

from __future__ import annotations

from typing import Any

import httpx2

from ..config import ARCHES, ORG, REGISTRY
from .http import request, request_json

Json = dict[str, Any]

MANIFEST_TYPES = (
    "application/vnd.oci.image.index.v1+json",
    "application/vnd.docker.distribution.manifest.list.v2+json",
    "application/vnd.oci.image.manifest.v1+json",
    "application/vnd.docker.distribution.manifest.v2+json",
)
"""What the hub accepts for a manifest: an index (per-platform manifests) or one image manifest."""

DOCKER_HUB = "registry-1.docker.io"
DOCKER_HUB_ALIASES = {"docker.io", "index.docker.io", DOCKER_HUB}
"""Docker Hub's names in an image reference; its registry API is on registry-1 and its tokens come from auth."""


def _token(http: httpx2.Client, registry: str, repository: str) -> str:
    scope = f"repository:{repository}:pull"
    if registry == DOCKER_HUB:
        url, params = "https://auth.docker.io/token", {"service": "registry.docker.io", "scope": scope}
    else:
        url, params = f"https://{registry}/token", {"scope": scope}
    token: str = request_json(http, "GET", url, params=params)["token"]
    return token


def ghcr_tags(http: httpx2.Client, name: str, *, org: str = ORG) -> list[str]:
    """Every tag of ghcr.io/<org>/<name>, following the registry's Link pagination; [] when the package is unknown."""
    repository = f"{org}/{name}"
    headers = {"Authorization": f"Bearer {_token(http, REGISTRY, repository)}"}
    url: str | None = f"https://{REGISTRY}/v2/{repository}/tags/list?n=1000"
    tags: list[str] = []
    while url:
        try:
            res = request(http, "GET", url, headers=headers)
        except httpx2.HTTPStatusError as e:
            if e.response.status_code == 404:
                return []
            raise
        tags.extend(res.json().get("tags") or [])
        link = res.headers.get("link", "")
        url = None
        if 'rel="next"' in link:
            next_path = link.split(";")[0].strip("<> ")
            url = next_path if next_path.startswith("https://") else f"https://{REGISTRY}{next_path}"
    return sorted(set(tags))


def parse_reference(image: str) -> tuple[str, str, str]:
    """
    `ghcr.io/linuxserver/baseimage-alpine:3.24` to (registry, repository, tag). A bare `owner/name` defaults to
    GHCR; Docker Hub references (`docker.io/alpine`, or a bare `alpine`) go to its registry host, official images
    under `library/`.
    """
    first, _, rest = image.partition("/")
    if rest and ("." in first or ":" in first or first == "localhost"):
        registry, path = first, rest
    elif not rest:
        registry, path = DOCKER_HUB, image
    else:
        registry, path = REGISTRY, image
    if registry in DOCKER_HUB_ALIASES:
        registry = DOCKER_HUB
        if "/" not in path.split("@")[0].split(":")[0]:
            path = f"library/{path}"
    if "@" in path:
        path, _, tag = path.partition("@")
    else:
        name, _, tag = path.rpartition(":")
        if name and "/" not in tag:
            path = name
        else:
            tag = "latest"
    return registry, path, tag


def _manifest(http: httpx2.Client, registry: str, repository: str, reference: str, headers: dict[str, str]) -> Json:
    url = f"https://{registry}/v2/{repository}/manifests/{reference}"
    body: Json = request_json(http, "GET", url, headers=headers)
    return body


def base_layers(http: httpx2.Client, image: str, digest: str | None) -> Json:
    """
    The compressed layer digests of a base image, per architecture, as the registry publishes them:
    `{"image", "digest", "platforms": {arch: {"digest", "layers": [...]}}}`. The build's `base.digest` is the
    digest of the index the build pulled, so it is fetched when given (a tag may have moved on since); a
    single-platform manifest is recorded for its one architecture.
    """
    registry, repository, tag = parse_reference(image)
    headers = {"Authorization": f"Bearer {_token(http, registry, repository)}", "Accept": ", ".join(MANIFEST_TYPES)}
    root = _manifest(http, registry, repository, digest or tag, headers)
    platforms: dict[str, Json] = {}
    if "manifests" in root:
        for entry in root["manifests"]:
            platform = entry.get("platform") or {}
            arch = platform.get("architecture")
            if platform.get("os") != "linux" or arch not in ARCHES or arch in platforms:
                continue
            manifest = _manifest(http, registry, repository, entry["digest"], headers)
            platforms[arch] = {"digest": entry["digest"], "layers": [layer["digest"] for layer in manifest["layers"]]}
    elif "layers" in root:
        config = root.get("config", {})
        arch = str(config.get("platform", {}).get("architecture") or "amd64")
        platforms[arch] = {"digest": digest, "layers": [layer["digest"] for layer in root["layers"]]}
    return {"image": image, "digest": digest, "platforms": dict(sorted(platforms.items()))}
