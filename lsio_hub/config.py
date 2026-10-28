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
PROOT_APPS_IMAGE = f"{IMAGE_PREFIX}/proot-apps"
PROOT_APPS_REPO = f"{ORG}/proot-apps"
STORE_REPOS = {"unraid": f"{ORG}/unraid-store", "umbrel": f"{ORG}/umbrel-store", "runtipi": f"{ORG}/runtipi-store"}
"""Platforms that read a git repository and want the store at its root: refresh.yml pushes out/stores/<platform>/
to these repositories (scripts/publish_store.sh); the repository URL is the import URL."""
UNRAID_RAW_URL = f"https://raw.githubusercontent.com/{STORE_REPOS['unraid']}/main"
"""Where each Unraid template's <TemplateURL> points, so Unraid updates it from the store repository."""

ARCHES = ("amd64", "arm64")
KEEP_BUILDS = 5
"""Builds kept in data/ per live branch, as many as each image repository's own Pages keeps (`repo_pages`); older
ones stay on their GitHub Release and in history.json."""
GITHUB_API = "https://api.github.com"
GITHUB = "https://github.com"


def repo_pages(repository: str) -> str:
    """
    The GitHub Pages site of an image repository (`docker-<name>` or `<owner>/docker-<name>`), without a trailing
    slash. Each image repository's build deploys the heavy files of its newest builds there:

        index.json                               {"schema": "lsio-pages/1", "repo", "generated_at", "keep", "builds"}
        builds/<tag>/files.<arch>.json.gz        the Release assets as they are (served as application/gzip)
        builds/<tag>/packages.<arch>.json.gz
        builds/<tag>/vulns.json                  the build's own vulnerability scan, as released (builder.derive.vulns)
        builds/<tag>/<arch>/screenshot.png ...   test.<arch>.tar.gz unpacked (REPORT_FILES, package_diff.txt)

    The hub copies none of it and links here instead. This is the one place the URL is derived: the domain
    changes at the cutover.
    """
    return f"https://{ORG}.github.io/{repository.rsplit('/', 1)[-1]}"


def build_pages(repository: str, tag: str) -> str:
    """A build's folder on its repository's Pages, with a trailing slash."""
    return f"{repo_pages(repository)}/builds/{tag}/"


def release_download(repository: str, tag: str, name: str) -> str:
    """A Release asset's download URL. For links only: Release assets send no CORS headers, so no browser can
    read one from another page."""
    return f"{GITHUB}/{repository}/releases/download/{tag}/{name}"


REPORT_FILES = {
    "screenshot": "screenshot.png",
    "container_log": "container.log",
    "browser_log": "browser.log",
    "sysinfo": "sysinfo.txt",
    "shellcheck": "shellcheck.xml",
}
"""test.<arch>.json `files` keys and the fixed names their files have under `builds/<tag>/<arch>/` on the
repository's Pages."""

WEBSITE = f"https://{ORG}.github.io/site/"
"""The LinuxServer.io site, which the hub's pages link to for images, builds, docs and support."""


def site_build(image: str, tag: str) -> str:
    """A build's page on the website, its CI results page (CONVENTIONS §10). The site renders every build the hub
    serves, including those newer than its own last build and those rotated out of data/ (its 404 page)."""
    return f"{WEBSITE}images/{image}/builds/{tag}/"


def site_builds(image: str) -> str:
    """The build list on an image's page on the website."""
    return f"{WEBSITE}images/{image}/#builds"


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
