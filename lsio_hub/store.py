"""
The data/ directory: what the ingest and the poller write and everything else reads. Raw inputs are kept
(manifests as fetched, build records as received) rather than finished responses, so a change to how a
field is derived needs no refetch, builds are deterministic and work offline, and every data commit is a
readable diff.

    data/images/<name>/manifest.<branch>.json      image.yml of each live branch, as JSON
    data/images/<name>/builds/<tag>.json           build.json of a live release, compact, as received
    data/images/<name>/builds/<tag>.diff.json      the diff against the previous build of the branch
    data/images/<name>/builds/<tag>.layers.<arch>.json
    data/images/<name>/builds/<tag>.test.<arch>.json    the ci test report (test.<arch>.json on the Release)
    data/images/<name>/builds/<tag>.vulns.<arch>.json   grype's matches against the build's SBOM, compact (poller)
    data/images/<name>/packages[.<release tag>].<arch>.json   normalised package table of the newest build
                                                   of each branch (no infix for the `latest` branch)
    data/images/<name>/latest.json                 branch -> newest build: tag, release url, asset urls
    data/images/<name>/history.json                branch -> every release seen, newest first
    data/bases/<algorithm>-<hex>.json              a base image's layer digests per architecture, keyed by the
                                                   index digest builds record as base.digest (registry cache)
    data/observed.json                             stars, archived flag, GHCR tags, the vulnerability scan ledger
                                                   (poller only)
    data/mods.json                                 the mods index
    data/proot-apps.json                           the PRoot Apps index (desktop apps)
    data/status/<source>.json                      refresh status of one source (manifests, releases, observed,
                                                   mods, proot-apps, vulnerabilities)
    data/status/rejected.json                      releases whose bundle failed validation
    data/status/bases.json                         base image lookups that failed, retried a day later

Every file has one writer: the ingest (images/, bases/, status/manifests, releases, rejected, bases) on the
release path, and the observer, the vulnerability scan and the mods and PRoot Apps refreshes (observed.json, mods.json,
proot-apps.json, their status files, the vulns files) on the hourly refresh. The two run concurrently and both commit
data/, so neither may write a file the other owns: saving writes a file only when its content changed.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import ARCHES

Json = dict[str, Any]

_BUILD_FILE = re.compile(r"^(?P<tag>.+?)(?:\.(?P<kind>diff|(?:layers|test|vulns)\.(?P<arch>amd64|arm64)))?\.json$")
_PACKAGES_FILE = re.compile(r"^packages(?:\.(?P<infix>.+))?\.(?P<arch>amd64|arm64)\.json$")
_MANIFEST_FILE = re.compile(r"^manifest\.(?P<branch>.+)\.json$")
STATUS_FILES = ("rejected", "bases")
"""Files under data/status/ that are not a source's status."""


@dataclass
class ImageRecord:
    """Everything data/ holds about one image. Dict keys are documented on the attributes."""

    name: str
    manifests: dict[str, Json] = field(default_factory=dict)
    """branch -> image.yml as JSON."""
    builds: dict[str, Json] = field(default_factory=dict)
    """release tag (4.0.20-ls1) -> build.json."""
    diffs: dict[str, Json] = field(default_factory=dict)
    """release tag -> diff.json."""
    layers: dict[str, dict[str, list[Json]]] = field(default_factory=dict)
    """release tag -> arch -> layers.<arch>.json."""
    tests: dict[str, dict[str, Json]] = field(default_factory=dict)
    """release tag -> arch -> test.<arch>.json."""
    vulns: dict[str, dict[str, Json]] = field(default_factory=dict)
    """release tag -> arch -> {db_date, grype_version, matches: [...]}, the newest build of each branch."""
    packages: dict[str, dict[str, Json]] = field(default_factory=dict)
    """branch -> arch -> {branch, release_tag, tag, arch, packages: [...]}, the newest build of the branch."""
    latest: dict[str, Json] = field(default_factory=dict)
    """branch -> {tag, release_tag, created, release_url, assets: {name: url}}."""
    history: dict[str, list[Json]] = field(default_factory=dict)
    """branch -> [{tag, created, release_url}], newest first, including builds rotated out of data/."""

    @property
    def default_branch(self) -> str | None:
        """The branch whose manifest publishes `latest`, else the first branch with a manifest."""
        for branch, manifest in self.manifests.items():
            if manifest.get("release", {}).get("tag") == "latest":
                return branch
        return next(iter(self.manifests), None)

    @property
    def manifest(self) -> Json | None:
        branch = self.default_branch
        return self.manifests[branch] if branch else None

    @property
    def kind(self) -> str:
        """`kind` of the default branch's manifest: `app`, or `base` / `tool` for images users do not run."""
        return str((self.manifest or {}).get("kind", "app"))

    def branch_of(self, release_tag: str) -> str | None:
        """The branch that publishes a release tag (`latest`, `develop`)."""
        for branch, manifest in self.manifests.items():
            if manifest.get("release", {}).get("tag") == release_tag:
                return branch
        return None

    def builds_of(self, branch: str) -> list[Json]:
        """Builds of a branch in data/, newest first."""
        found = [b for b in self.builds.values() if b.get("branch") == branch]
        return sorted(found, key=lambda b: (b["created"], b["version"].get("ls_build", 0)), reverse=True)

    def latest_build(self, branch: str | None = None) -> Json | None:
        branch = branch or self.default_branch
        if branch is None:
            return None
        builds = self.builds_of(branch)
        return builds[0] if builds else None

    def sorted_builds(self) -> list[Json]:
        """Every build in data/, newest first."""
        return sorted(self.builds.values(), key=lambda b: (b["created"], b["version"].get("ls_build", 0)), reverse=True)


@dataclass
class Store:
    images: dict[str, ImageRecord] = field(default_factory=dict)
    observed: Json = field(default_factory=dict)
    """{fetched_at, images: {name: {stars, archived, pushed_at, ghcr_tags}}, vulnerabilities: {db_date, grype_version,
    checked_at, builds: {"<image>@<tag>": {scanned_at, db_date, arches}}}}"""
    mods: Json = field(default_factory=dict)
    """{fetched_at, source, mods: [...]}"""
    proot_apps: Json = field(default_factory=dict)
    """{fetched_at, source, cli, apps: [...]}"""
    bases: dict[str, Json] = field(default_factory=dict)
    """base digest -> {image, digest, fetched_at, platforms: {arch: {digest, layers: [digests]}}}"""
    status: Json = field(default_factory=lambda: {"sources": {}, "rejected": {}, "bases": {}})
    """{sources: {name: SourceStatus}, rejected: {"<image>@<tag>": {checked_at, release_url, error}},
    bases: {base digest: {image, checked_at, error}}}"""

    def record(self, name: str) -> ImageRecord:
        return self.images.setdefault(name, ImageRecord(name=name))

    def base_digests(self) -> set[str]:
        """Every base digest a held build records."""
        return {
            digest
            for record in self.images.values()
            for build in record.builds.values()
            if (digest := build.get("base", {}).get("digest"))
        }


def base_filename(digest: str) -> str:
    """`sha256:abc...` to `sha256-abc....json`: the colon is unwelcome in file names."""
    return digest.replace(":", "-") + ".json"


# ---------------------------------------------------------------------------------------------------
# Reading


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def load_record(directory: Path) -> ImageRecord:
    record = ImageRecord(name=directory.name)
    for path in sorted(directory.glob("manifest.*.json")):
        m = _MANIFEST_FILE.match(path.name)
        if m:
            record.manifests[m["branch"]] = _read(path)
    for path in sorted((directory / "builds").glob("*.json")) if (directory / "builds").is_dir() else []:
        m = _BUILD_FILE.match(path.name)
        if not m:
            continue
        tag, kind = m["tag"], m["kind"]
        if kind is None:
            record.builds[tag] = _read(path)
        elif kind == "diff":
            record.diffs[tag] = _read(path)
        elif kind.startswith("layers."):
            record.layers.setdefault(tag, {})[m["arch"]] = _read(path)
        elif kind.startswith("vulns."):
            record.vulns.setdefault(tag, {})[m["arch"]] = _read(path)
        else:
            record.tests.setdefault(tag, {})[m["arch"]] = _read(path)
    for path in sorted(directory.glob("packages.*.json")):
        m = _PACKAGES_FILE.match(path.name)
        if m:
            table = _read(path)
            record.packages.setdefault(table["branch"], {})[m["arch"]] = table
    record.latest = _read(directory / "latest.json") or {}
    record.history = _read(directory / "history.json") or {}
    return record


def load_store(data_dir: Path) -> Store:
    """Reads data/. Missing files are treated as empty so a fresh checkout can ingest straight away."""
    store = Store()
    images_dir = data_dir / "images"
    if images_dir.is_dir():
        for directory in sorted(p for p in images_dir.iterdir() if p.is_dir()):
            store.images[directory.name] = load_record(directory)
    bases_dir = data_dir / "bases"
    for path in sorted(bases_dir.glob("*.json")) if bases_dir.is_dir() else []:
        base = _read(path)
        if isinstance(base, dict) and base.get("digest"):
            store.bases[base["digest"]] = base
    store.observed = _read(data_dir / "observed.json") or {}
    store.mods = _read(data_dir / "mods.json") or {}
    store.proot_apps = _read(data_dir / "proot-apps.json") or {}
    legacy = _read(data_dir / "status.json") or {}  # one file for every source before status/ was split
    status_dir = data_dir / "status"
    sources = dict(legacy.get("sources", {}))
    for path in sorted(status_dir.glob("*.json")) if status_dir.is_dir() else []:
        if path.stem not in STATUS_FILES:
            sources[path.stem] = _read(path)
    store.status = {
        "sources": sources,
        "rejected": _read(status_dir / "rejected.json") or legacy.get("rejected", {}),
        "bases": _read(status_dir / "bases.json") or {},
    }
    return store


# ---------------------------------------------------------------------------------------------------
# Writing


def _dump(value: Any, *, compact: bool = False) -> str:
    if compact:
        return json.dumps(value, separators=(",", ":"), ensure_ascii=False) + "\n"
    return json.dumps(value, indent=1, ensure_ascii=False) + "\n"


def _write(path: Path, text: str, written: set[Path]) -> bool:
    """Writes only when the content differs; returns whether it did."""
    written.add(path)
    if path.is_file() and path.read_text(encoding="utf-8") == text:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return True


def packages_filename(release_tag: str, arch: str) -> str:
    """packages.amd64.json for the latest branch, packages.develop.amd64.json for the others."""
    return f"packages.{arch}.json" if release_tag == "latest" else f"packages.{release_tag}.{arch}.json"


def record_files(record: ImageRecord) -> dict[str, str]:
    """Every file of an image directory as {relative path: text}."""
    files: dict[str, str] = {}
    for branch, manifest in sorted(record.manifests.items()):
        files[f"manifest.{branch}.json"] = _dump(manifest)
    for tag, build in sorted(record.builds.items()):
        files[f"builds/{tag}.json"] = _dump(build, compact=True)
    for tag, diff in sorted(record.diffs.items()):
        if tag in record.builds:
            files[f"builds/{tag}.diff.json"] = _dump(diff)
    for tag, per_arch in sorted(record.layers.items()):
        if tag in record.builds:
            for arch in ARCHES:
                if arch in per_arch:
                    files[f"builds/{tag}.layers.{arch}.json"] = _dump(per_arch[arch], compact=True)
    for tag, reports in sorted(record.tests.items()):
        if tag in record.builds:
            for arch in ARCHES:
                if arch in reports:
                    files[f"builds/{tag}.test.{arch}.json"] = _dump(reports[arch], compact=True)
    for tag, scans in sorted(record.vulns.items()):
        if tag in record.builds:
            for arch in ARCHES:
                if arch in scans:
                    files[f"builds/{tag}.vulns.{arch}.json"] = _dump(scans[arch], compact=True)
    for tables in record.packages.values():
        for arch, table in tables.items():
            files[packages_filename(table["release_tag"], arch)] = _dump(table, compact=True)
    files["latest.json"] = _dump(dict(sorted(record.latest.items())))
    files["history.json"] = _dump(dict(sorted(record.history.items())))
    return files


def save_record(images_dir: Path, record: ImageRecord) -> list[str]:
    """Writes an image directory and removes files that no longer belong (rotated builds, gone branches)."""
    directory = images_dir / record.name
    written: set[Path] = set()
    changed = [rel for rel, text in record_files(record).items() if _write(directory / rel, text, written)]
    for path in list(directory.glob("*.json")) + list((directory / "builds").glob("*.json")):
        if path not in written:
            path.unlink()
            changed.append(f"-{path.relative_to(directory)}")
    return changed


def save_store(data_dir: Path, store: Store) -> list[str]:
    """Writes data/; returns the relative paths that changed (prefixed with - when removed)."""
    changed: list[str] = []
    images_dir = data_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    for name, record in sorted(store.images.items()):
        changed += [f"images/{name}/{rel}" for rel in save_record(images_dir, record)]
    for directory in images_dir.iterdir():
        if directory.is_dir() and directory.name not in store.images:
            for path in sorted(directory.rglob("*"), reverse=True):
                path.unlink() if path.is_file() else path.rmdir()
            directory.rmdir()
            changed.append(f"-images/{directory.name}")
    written: set[Path] = set()
    referenced = store.base_digests()
    for digest, base in sorted(store.bases.items()):
        if digest in referenced and _write(data_dir / "bases" / base_filename(digest), _dump(base), written):
            changed.append(f"bases/{base_filename(digest)}")
    bases_dir = data_dir / "bases"
    for path in sorted(bases_dir.glob("*.json")) if bases_dir.is_dir() else []:
        if path not in written:
            path.unlink()
            changed.append(f"-bases/{path.name}")
    files: list[tuple[str, Any]] = [("observed.json", store.observed), ("mods.json", store.mods)]
    files.append(("proot-apps.json", store.proot_apps))
    files += [(f"status/{source}.json", value) for source, value in sorted(store.status["sources"].items())]
    files += [(f"status/{name}.json", store.status.get(name, {})) for name in STATUS_FILES]
    for name, value in files:
        if _write(data_dir / name, _dump(value), written):
            changed.append(name)
    for path in [data_dir / "status.json", *sorted((data_dir / "status").glob("*.json"))]:
        if path.is_file() and path not in written:
            path.unlink()
            changed.append(f"-{path.relative_to(data_dir)}")
    return changed
