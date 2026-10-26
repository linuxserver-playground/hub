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

__all__ = ["base_layers", "ghcr_tags", "parse_reference"]


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
