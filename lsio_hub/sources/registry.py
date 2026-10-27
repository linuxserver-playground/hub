"""
Registries, read anonymously: the tag list of a public GHCR package and the layer digests of a base image on
GHCR or Docker Hub. Both hand out a pull token without credentials; nothing here needs GITHUB_TOKEN. The
reference parsing and the base lookup are the builder's (`builder.derive.registry`, which the build runs for its
record.json), here with the hub's HTTP client and its retries.
"""

from __future__ import annotations

from typing import Any

import httpx2
from builder.derive import registry as shared
from builder.derive.registry import parse_reference

from ..config import ORG, REGISTRY
from .http import request, request_json

Json = dict[str, Any]

__all__ = ["GhcrPackage", "base_layers", "ghcr_tags", "parse_reference"]


def _getter(http: httpx2.Client) -> shared.Get:
    def get(url: str, params: dict[str, str], headers: dict[str, str]) -> Json:
        body: Json = request_json(http, "GET", url, params=params or None, headers=headers)
        return body

    return get


def ghcr_tags(http: httpx2.Client, name: str, *, org: str = ORG) -> list[str]:
    """Every tag of ghcr.io/<org>/<name>, following the registry's Link pagination; [] when the package is unknown."""
    repository = f"{org}/{name}"
    headers = {"Authorization": f"Bearer {shared.token(_getter(http), REGISTRY, repository)}"}
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


def base_layers(http: httpx2.Client, image: str, digest: str | None) -> Json:
    """
    The compressed layer digests of a base image, per architecture, as the registry publishes them:
    `{"image", "digest", "platforms": {arch: {"digest", "layers": [...]}}}` (see `builder.derive.registry`).
    """
    base: Json = shared.base_layers(image, digest, _getter(http))
    return base


class GhcrPackage:
    """One public GHCR package read with one anonymous pull token: its tag list and, per tag, what was built (the
    image's digest, its config's `created` time and the version and revision labels the build set)."""

    def __init__(self, http: httpx2.Client, name: str, *, org: str = ORG) -> None:
        self.http = http
        self.name, self.org = name, org
        self.repository = f"{org}/{name}"
        self._headers: dict[str, str] | None = None

    def headers(self) -> dict[str, str]:
        if self._headers is None:
            token = shared.token(_getter(self.http), REGISTRY, self.repository)
            self._headers = {"Authorization": f"Bearer {token}", "Accept": ", ".join(shared.MANIFEST_TYPES)}
        return self._headers

    def tags(self) -> list[str]:
        return ghcr_tags(self.http, self.name, org=self.org)

    def _manifest(self, reference: str) -> tuple[str, Json]:
        url = f"https://{REGISTRY}/v2/{self.repository}/manifests/{reference}"
        res = request(self.http, "GET", url, headers=self.headers())
        return res.headers.get("docker-content-digest", ""), res.json()

    def image(self, tag: str, known: Json | None = None) -> Json:
        """`{digest, created, version, revision}` of a tag. One request when the digest is still `known`'s (whose
        values are then kept); otherwise the amd64 (or first linux) manifest and its config as well."""
        digest, root = self._manifest(tag)
        if known and digest and known.get("digest") == digest:
            return {k: known.get(k) for k in ("digest", "created", "version", "revision")}
        manifest = root
        if "manifests" in root:
            linux = [m for m in root["manifests"] if (m.get("platform") or {}).get("os") == "linux"]
            linux.sort(key=lambda m: (m.get("platform") or {}).get("architecture") != "amd64")
            if not linux:
                return {"digest": digest, "created": None, "version": None, "revision": None}
            manifest = self._manifest(linux[0]["digest"])[1]
        config_digest = (manifest.get("config") or {}).get("digest")
        config: Json = {}
        if config_digest:
            url = f"https://{REGISTRY}/v2/{self.repository}/blobs/{config_digest}"
            config = request(self.http, "GET", url, headers={"Authorization": self.headers()["Authorization"]}).json()
        labels = (config.get("config") or {}).get("Labels") or {}
        return {
            "digest": digest or None,
            "created": config.get("created"),
            "version": labels.get("org.opencontainers.image.version") or None,
            "revision": labels.get("org.opencontainers.image.revision") or None,
        }
