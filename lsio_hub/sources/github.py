"""
GitHub as the hub sees it: the organisation's image repositories, a file at a ref, the releases of a
repository and their assets. REST with GITHUB_TOKEN (fine-grained enough for public repos in the org; the
anonymous limit of 60 requests an hour is not).
"""

from __future__ import annotations

import base64
from typing import Any

import httpx2

from ..config import GITHUB_API
from .http import request, request_json

Json = dict[str, Any]

REPO_QUERY = """
query ($org: String!, $cursor: String) {
  organization(login: $org) {
    repositories(first: 100, after: $cursor, orderBy: { field: NAME, direction: ASC }) {
      pageInfo { hasNextPage endCursor }
      nodes { name url stargazerCount pushedAt isArchived defaultBranchRef { name } }
    }
  }
}"""


def is_image_repo(repo_name: str) -> bool:
    """Image repositories are docker-<name>; docker-mods is the mods repository, not an image."""
    return repo_name.startswith("docker-") and repo_name != "docker-mods"


class GitHub:
    def __init__(self, http: httpx2.Client, token: str | None) -> None:
        self.http = http
        self.headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        if token:
            self.headers["Authorization"] = f"Bearer {token}"

    def get(self, path: str, **params: Any) -> Any:
        url = path if path.startswith("https://") else f"{GITHUB_API}/{path.lstrip('/')}"
        return request_json(self.http, "GET", url, headers=self.headers, params=params or None)

    def paginate(self, path: str, *, per_page: int = 100, max_pages: int = 10, **params: Any) -> list[Json]:
        items: list[Json] = []
        for page in range(1, max_pages + 1):
            batch = self.get(path, per_page=per_page, page=page, **params)
            items.extend(batch)
            if len(batch) < per_page:
                break
        return items

    def graphql(self, query: str, variables: Json) -> Json:
        res = request_json(
            self.http,
            "POST",
            f"{GITHUB_API}/graphql",
            headers=self.headers,
            json={"query": query, "variables": variables},
        )
        if res.get("errors"):
            raise RuntimeError("GitHub GraphQL: " + "; ".join(e["message"] for e in res["errors"]))
        data: Json = res["data"]
        return data

    def org_repos(self, org: str) -> list[Json]:
        """Every repository of the organisation (GraphQL, 100 a page) with stars, archived flag and default branch."""
        repos: list[Json] = []
        cursor = None
        while True:
            data = self.graphql(REPO_QUERY, {"org": org, "cursor": cursor})
            page = (data.get("organization") or {}).get("repositories")
            if not page:
                raise RuntimeError(f"GitHub GraphQL: organization {org} not found")
            for node in page["nodes"]:
                repos.append(
                    {
                        "name": node["name"],
                        "url": node["url"],
                        "stars": node["stargazerCount"],
                        "pushed_at": node.get("pushedAt"),
                        "archived": node["isArchived"],
                        "default_branch": (node.get("defaultBranchRef") or {}).get("name") or "main",
                    }
                )
            if not page["pageInfo"]["hasNextPage"]:
                return repos
            cursor = page["pageInfo"]["endCursor"]

    def file_text(self, repo: str, path: str, ref: str) -> str | None:
        """The text of a file at a ref, or None when the file or the ref does not exist."""
        try:
            res = self.get(f"repos/{repo}/contents/{path}", ref=ref)
        except httpx2.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise
        if res.get("encoding") != "base64":
            return None
        return base64.b64decode(res["content"]).decode("utf-8")

    def releases(self, repo: str, *, max_pages: int = 3) -> list[Json]:
        """Published (non-draft) releases, newest first as GitHub lists them."""
        return [r for r in self.paginate(f"repos/{repo}/releases", max_pages=max_pages) if not r.get("draft")]

    def release_by_tag(self, repo: str, tag: str) -> Json:
        release: Json = self.get(f"repos/{repo}/releases/tags/{tag}")
        return release

    def download(self, url: str) -> bytes:
        """A release asset. The API asset URL needs Accept: application/octet-stream; browser URLs don't mind it."""
        headers = {**self.headers, "Accept": "application/octet-stream"}
        return request(self.http, "GET", url, headers=headers).content
