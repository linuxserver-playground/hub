"""Paths, namespaces and the site configuration. Nothing here is read from the network."""

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DIST_DIR = ROOT / "dist"
OUT_DIR = ROOT / "out"
PUBLIC_DIR = ROOT / "public"

ORG = "linuxserver-playground"
REGISTRY = "ghcr.io"
IMAGE_PREFIX = f"{REGISTRY}/{ORG}"
MODS_IMAGE = f"{IMAGE_PREFIX}/mods"
MODS_REPO = f"{ORG}/docker-mods"
STORE_REPOS = {"unraid": f"{ORG}/unraid-store", "umbrel": f"{ORG}/umbrel-store", "runtipi": f"{ORG}/runtipi-store"}
"""Platforms that read a git repository and want the store at its root: deploy.yml pushes out/stores/<platform>/
to these repositories (scripts/publish_store.sh); the repository URL is the import URL."""
UNRAID_RAW_URL = f"https://raw.githubusercontent.com/{STORE_REPOS['unraid']}/main"
"""Where each Unraid template's <TemplateURL> points, so Unraid updates it from the store repository."""

ARCHES = ("amd64", "arm64")
KEEP_BUILDS = 10
"""Builds kept in data/ per live branch; older ones stay on their GitHub Release and in history.json."""
GITHUB_API = "https://api.github.com"


@dataclass(frozen=True)
class SiteConfig:
    site_url: str = "http://localhost:8000"
    """Origin the site is served from, e.g. https://linuxserver-playground.github.io"""
    base_path: str = "/"
    """Path prefix, with leading and trailing slash: "/" or "/hub/"."""

    @classmethod
    def from_env(cls) -> "SiteConfig":
        """SITE_URL and BASE_PATH come from actions/configure-pages in CI."""
        site_url = (os.environ.get("SITE_URL") or cls.site_url).rstrip("/")
        base = os.environ.get("BASE_PATH", "").strip("/")
        return cls(site_url=site_url, base_path=f"/{base}/" if base else "/")

    @property
    def site_root(self) -> str:
        """The site's public URL, with a trailing slash."""
        return f"{self.site_url}{self.base_path}"

    @property
    def api_root(self) -> str:
        """The API's base URL for `servers` and examples, without a trailing slash."""
        return self.site_root.rstrip("/")

    @property
    def stores_root(self) -> str:
        """Where the Pages deployment serves the generated store output, without a trailing slash."""
        return f"{self.site_root}stores"
