"""GHCR, read anonymously: the tag list of a public package. The registry hands out a pull token without credentials."""

from __future__ import annotations

import httpx2

from ..config import ORG, REGISTRY
from .http import request, request_json


def ghcr_tags(http: httpx2.Client, name: str, *, org: str = ORG) -> list[str]:
    """Every tag of ghcr.io/<org>/<name>, following the registry's Link pagination; [] when the package is unknown."""
    repository = f"{org}/{name}"
    token = request_json(http, "GET", f"https://{REGISTRY}/token", params={"scope": f"repository:{repository}:pull"})[
        "token"
    ]
    headers = {"Authorization": f"Bearer {token}"}
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
