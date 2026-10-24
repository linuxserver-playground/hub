"""
Ingests build bundles and manifests into data/.

    python -m lsio_hub.ingest --reconcile              every docker-* repo in the org: manifests of every
                                                       live branch, every release not yet in data/
    python -m lsio_hub.ingest --repo owner/name --tag x one release (the repository_dispatch payload)

A release is ingested once: its build.json is downloaded, validated against the bundle contract, the
package tables and layer lists fetched, the diff against the previous build of the branch computed and
everything written to data/. A release whose bundle does not validate is recorded in status.json under
`rejected` with the error and retried on the next run. Nothing here deletes data on failure: a source that
cannot be reached keeps its previous data and the failure is recorded, as static-api did.
"""

from __future__ import annotations

import argparse
import datetime
import json
import logging
import os
import sys
from collections.abc import Callable
from typing import Any

import httpx2
import yaml
from builder.manifest import load_manifest_text
from contracts import ContractError, validate

from . import packages as pkg
from .config import ARCHES, DATA_DIR, KEEP_BUILDS, ORG
from .diff import diff_builds
from .sources.github import GitHub, is_image_repo
from .sources.http import client
from .store import ImageRecord, Store, load_store, save_store

log = logging.getLogger(__name__)
Json = dict[str, Any]
Now = Callable[[], str]


def _now() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class IngestError(Exception):
    """A release that cannot be ingested; the message goes to status.json."""


def image_name(repo_name: str) -> str:
    return repo_name.removeprefix("docker-")


# ---------------------------------------------------------------------------------------------------
# Manifests


def parse_manifest(text: str) -> Json:
    """image.yml text to a validated dict. Raises IngestError with the contract's message."""
    try:
        data = load_manifest_text(text)
    except yaml.YAMLError as e:
        raise IngestError(f"image.yml is not valid YAML: {e}") from e
    if not isinstance(data, dict):
        raise IngestError("image.yml is not a mapping")
    try:
        validate("image", data)
    except ContractError as e:
        raise IngestError(f"image.yml does not validate: {e}") from e
    return data


def fetch_manifests(gh: GitHub, repo: str, default_branch: str) -> dict[str, Json]:
    """
    The manifest of every live branch: the default branch's image.yml, then one branch per tag in its
    `release.tags` whose own image.yml publishes that tag (the branch is named after the tag, per the conventions).
    """
    text = gh.file_text(repo, "image.yml", default_branch)
    if text is None:
        raise IngestError(f"no image.yml on {default_branch}")
    manifest = parse_manifest(text)
    manifests = {manifest["release"]["branch"]: manifest}
    seen_tags = {manifest["release"]["tag"]}
    for entry in manifest["release"].get("tags", []):
        tag = entry["tag"]
        if tag in seen_tags:
            continue
        seen_tags.add(tag)
        other = gh.file_text(repo, "image.yml", tag)
        if other is None:
            log.info("  %s: tag %s has no branch of that name with an image.yml; not a live branch", repo, tag)
            continue
        try:
            data = parse_manifest(other)
        except IngestError as e:
            log.warning("  %s@%s: %s", repo, tag, e)
            continue
        if data["release"]["tag"] != tag:
            log.warning("  %s@%s: its image.yml publishes %s, not %s", repo, tag, data["release"]["tag"], tag)
            continue
        manifests[data["release"]["branch"]] = data
    return manifests


# ---------------------------------------------------------------------------------------------------
# Releases


def _asset_map(release: Json) -> dict[str, Json]:
    return {a["name"]: a for a in release.get("assets", [])}


def validate_bundle(data: Any, release: Json, name: str, live_branches: set[str]) -> Json:
    try:
        validate("bundle", data)
    except ContractError as e:
        raise IngestError(f"build.json does not validate: {e}") from e
    bundle: Json = data
    if bundle["mode"] != "live":
        raise IngestError(f"build.json is a {bundle['mode']} build, not a live release")
    if bundle["image"] != name:
        raise IngestError(f"build.json is for image {bundle['image']!r}, expected {name!r}")
    if bundle["version"]["tag"] != release["tag_name"]:
        raise IngestError(f"build.json version.tag {bundle['version']['tag']!r} differs from the release tag")
    if bundle["branch"] not in live_branches:
        raise IngestError(f"build.json branch {bundle['branch']!r} is not a live branch of the image")
    return bundle


def _previous(record: ImageRecord, bundle: Json) -> Json | None:
    """The build this one follows: the newest earlier build of the same branch in data/."""
    earlier = [
        b
        for b in record.builds_of(bundle["branch"])
        if (b["created"], b["version"].get("ls_build", 0)) < (bundle["created"], bundle["version"].get("ls_build", 0))
    ]
    return earlier[0] if earlier else None


def _history_entry(bundle: Json, release: Json) -> Json:
    return {"tag": bundle["version"]["tag"], "created": bundle["created"], "release_url": release.get("html_url")}


def ingest_release(gh: GitHub, record: ImageRecord, release: Json) -> Json:
    """Downloads, validates and stores one release. Returns the bundle. Raises IngestError when it cannot."""
    assets = _asset_map(release)
    if "build.json" not in assets:
        raise IngestError("release has no build.json asset")
    try:
        raw = json.loads(gh.download(assets["build.json"]["url"]))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise IngestError(f"build.json is not JSON: {e}") from e
    bundle = validate_bundle(raw, release, record.name, set(record.manifests))
    tag, branch = bundle["version"]["tag"], bundle["branch"]
    release_tag = bundle["version"].get("release_tag") or record.manifests.get(branch, {}).get("release", {}).get("tag")
    if release_tag is None:
        release_tag = "latest" if branch == record.default_branch else branch
    successful = [p["arch"] for p in bundle["platforms"] if p["result"] == "success" and p["arch"] in ARCHES]

    layers: dict[str, list[Json]] = {}
    tests: dict[str, Json] = {}
    tables: dict[str, Json] = {}
    for arch in ARCHES:
        test_asset = assets.get(f"test.{arch}.json")
        if test_asset:
            try:
                report = json.loads(gh.download(test_asset["url"]))
                validate("test-report", report)
                tests[arch] = report
            except (json.JSONDecodeError, UnicodeDecodeError, ContractError) as e:
                log.warning("  %s@%s: test.%s.json unusable: %s", record.name, tag, arch, e)
    for arch in successful:
        layer_asset = assets.get(f"layers.{arch}.json")
        if layer_asset:
            try:
                layers[arch] = json.loads(gh.download(layer_asset["url"]))
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                log.warning("  %s@%s: layers.%s.json unreadable: %s", record.name, tag, arch, e)
        package_asset = assets.get(f"packages.{arch}.json.gz")
        if package_asset:
            try:
                rows = pkg.normalise_gz(gh.download(package_asset["url"]))
            except (OSError, ValueError) as e:
                log.warning("  %s@%s: packages.%s.json.gz unreadable: %s", record.name, tag, arch, e)
            else:
                tables[arch] = pkg.table(record.name, branch, release_tag, tag, arch, rows)

    previous = _previous(record, bundle)
    old_tables = record.packages.get(branch, {})
    old_packages = (
        {arch: t["packages"] for arch, t in old_tables.items()}
        if previous and old_tables and all(t["tag"] == previous["version"]["tag"] for t in old_tables.values())
        else None
    )
    new_packages = {arch: t["packages"] for arch, t in tables.items()} or None
    record.builds[tag] = bundle
    record.diffs[tag] = diff_builds(bundle, previous, new_packages, old_packages)
    if layers:
        record.layers[tag] = layers
    if tests:
        record.tests[tag] = tests
    newest = record.builds_of(branch)[0]
    if newest["version"]["tag"] == tag:
        if tables:
            record.packages[branch] = tables
        record.latest[branch] = {
            "tag": tag,
            "release_tag": release_tag,
            "created": bundle["created"],
            "release_url": release.get("html_url"),
            "assets": {name: a.get("browser_download_url") for name, a in sorted(assets.items())},
        }
    history = [h for h in record.history.get(branch, []) if h["tag"] != tag]
    history.append(_history_entry(bundle, release))
    record.history[branch] = sorted(history, key=lambda h: h["created"], reverse=True)
    return bundle


def rotate(record: ImageRecord, keep: int = KEEP_BUILDS) -> list[str]:
    """Keeps the newest `keep` builds per branch in data/; the rest stay on their Release and in history.json."""
    dropped: list[str] = []
    for branch in {b["branch"] for b in record.builds.values()}:
        for build in record.builds_of(branch)[keep:]:
            tag = build["version"]["tag"]
            record.builds.pop(tag, None)
            record.diffs.pop(tag, None)
            record.layers.pop(tag, None)
            record.tests.pop(tag, None)
            dropped.append(tag)
    return dropped


def _reject(store: Store, record: ImageRecord, release: Json, error: str, now: Now) -> None:
    key = f"{record.name}@{release.get('tag_name', '?')}"
    store.status["rejected"][key] = {"checked_at": now(), "release_url": release.get("html_url"), "error": error}
    log.warning("  ! %s: %s", key, error)


def _accept(store: Store, record: ImageRecord, release: Json) -> None:
    store.status["rejected"].pop(f"{record.name}@{release.get('tag_name', '?')}", None)


def guess_branch(record: ImageRecord, release: Json) -> str | None:
    """
    The live branch a release belongs to. The conventions say `target_commitish` is the branch name; the
    shared workflow currently writes the commit sha, so the tag prefix (`develop-...`) decides, then the
    default branch. `ingest_release` checks the guess against `branch` in the bundle.
    """
    target = str(release.get("target_commitish", ""))
    if target in record.manifests:
        return target
    tag_name = str(release.get("tag_name", ""))
    for branch, manifest in record.manifests.items():
        release_tag = manifest["release"]["tag"]
        if release_tag != "latest" and tag_name.startswith(f"{release_tag}-"):
            return branch
    return record.default_branch


def pending_releases(record: ImageRecord, releases: list[Json], keep: int = KEEP_BUILDS) -> list[Json]:
    """Releases of live branches not yet in data/, newest `keep` per branch, oldest first so diffs chain."""
    by_branch: dict[str, list[Json]] = {}
    for release in releases:
        branch = guess_branch(record, release)
        if branch is not None:
            by_branch.setdefault(branch, []).append(release)
    pending: list[Json] = []
    for branch_releases in by_branch.values():
        newest = sorted(branch_releases, key=lambda r: r.get("created_at", ""), reverse=True)[:keep]
        pending.extend(r for r in newest if r["tag_name"] not in record.builds)
    return sorted(pending, key=lambda r: r.get("created_at", ""))


def ingest_repo(store: Store, gh: GitHub, repo: Json, now: Now) -> None:
    """Manifests of every live branch, then every pending release, for one image repository."""
    name = image_name(repo["name"])
    full = f"{ORG}/{repo['name']}"
    record = store.record(name)
    record.manifests = fetch_manifests(gh, full, repo["default_branch"])
    releases = gh.releases(full)
    for release in pending_releases(record, releases):
        try:
            bundle = ingest_release(gh, record, release)
        except (IngestError, httpx2.HTTPError) as e:
            _reject(store, record, release, str(e), now)
            continue
        _accept(store, record, release)
        log.info(
            "  + %s@%s (%s)", name, bundle["version"]["tag"], record.diffs[bundle["version"]["tag"]]["classification"]
        )
    rotate(record)


def _set_status(store: Store, source: str, ok: bool, now: Now, error: str | None = None) -> None:
    previous = store.status["sources"].get(source, {})
    status = {"ok": ok, "checked_at": now(), "fetched_at": now() if ok else previous.get("fetched_at")}
    if error:
        status["error"] = error
    store.status["sources"][source] = {k: v for k, v in status.items() if v is not None}


def reconcile(store: Store, gh: GitHub, now: Now = _now) -> None:
    """Every docker-* repository in the organisation. Repositories that fail keep their previous data."""
    try:
        repos = [r for r in gh.org_repos(ORG) if is_image_repo(r["name"])]
    except (httpx2.HTTPError, RuntimeError) as e:
        _set_status(store, "manifests", False, now, f"listing repositories: {e}")
        _set_status(store, "releases", False, now, f"listing repositories: {e}")
        return
    failures: list[str] = []
    for repo in repos:
        log.info("%s", repo["name"])
        try:
            ingest_repo(store, gh, repo, now)
        except (IngestError, httpx2.HTTPError) as e:
            failures.append(f"{repo['name']}: {e}")
            log.warning("  ! %s: %s (keeping previous data)", repo["name"], e)
    names = {image_name(r["name"]) for r in repos}
    for gone in sorted(set(store.images) - names):
        log.info("  - %s: repository no longer in the organisation; removing its data", gone)
        store.images.pop(gone)
    error = "; ".join(failures) if failures else None
    _set_status(store, "manifests", not failures, now, error)
    _set_status(store, "releases", not failures, now, error)


def ingest_one(store: Store, gh: GitHub, repo: str, tag: str, now: Now = _now) -> bool:
    """One release by repository and tag, as sent by repository_dispatch. Returns whether it was stored."""
    owner, _, repo_name = repo.partition("/")
    if owner != ORG or not is_image_repo(repo_name):
        raise IngestError(f"{repo} is not an image repository of {ORG}")
    name = image_name(repo_name)
    record = store.record(name)
    default_branch = gh.get(f"repos/{repo}")["default_branch"]
    record.manifests = fetch_manifests(gh, repo, default_branch)
    try:
        release = gh.release_by_tag(repo, tag)
    except httpx2.HTTPStatusError as e:
        if e.response.status_code == 404:
            # A dispatch for a run that released nothing (or a release deleted since): nothing to ingest,
            # and not a deploy failure. The hourly reconcile catches anything that appears later.
            log.warning("%s has no release %s; nothing to ingest", repo, tag)
            return False
        raise
    if tag in record.builds:
        log.info("%s@%s already ingested", name, tag)
        return False
    try:
        ingest_release(gh, record, release)
    except (IngestError, httpx2.HTTPError) as e:
        _reject(store, record, release, str(e), now)
        return False
    _accept(store, record, release)
    rotate(record)
    _set_status(store, "releases", True, now)
    return True


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("httpx2").setLevel(logging.WARNING)
    parser = argparse.ArgumentParser(description="Ingest manifests and build bundles into data/.")
    parser.add_argument("--reconcile", action="store_true", help="every repository and release in the organisation")
    parser.add_argument("--repo", help="owner/name of one image repository")
    parser.add_argument("--tag", help="the release tag to ingest from --repo")
    args = parser.parse_args(argv)
    if not args.reconcile and not (args.repo and args.tag):
        parser.error("use --reconcile, or --repo owner/name --tag x")
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        log.warning("GITHUB_TOKEN is not set; anonymous GitHub requests are rate limited to 60 an hour")
    store = load_store(DATA_DIR)
    gh = GitHub(client(), token)
    if args.reconcile:
        reconcile(store, gh)
    else:
        ingest_one(store, gh, args.repo, args.tag)
    changed = save_store(DATA_DIR, store)
    log.info("%d files changed in data/", len(changed))
    for source, status in store.status["sources"].items():
        if not status.get("ok") and os.environ.get("GITHUB_ACTIONS"):
            message = str(status.get("error", "")).replace("%", "%25").replace("\n", "%0A")
            print(f"::warning title={source} refresh failed::{message}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
