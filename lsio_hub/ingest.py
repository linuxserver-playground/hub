"""
Ingests build bundles and manifests into data/.

    python -m lsio_hub.ingest --reconcile [--deep]     every docker-* repo in the org: manifests of every
                                                       live branch, every release not yet in data/
    python -m lsio_hub.ingest --repo owner/name --tag x one release

A release is ingested once: its build.json is downloaded and validated against the bundle contract, then its
record.json, in which the build derived the package tables, the diff against the previous release, its
vulnerability scan and its base image's layers (CONVENTIONS §6). A release without one (made before records
existed) has its package documents, layer lists and test reports fetched and the diff computed here, with the
same code (builder.derive). Everything is written to data/. The layer digests of every base image a held
build was built from come from its record, or else from the registry, once per base digest (data/bases/), so
the layers endpoint can tell base layers from the image's own. A release whose bundle does not validate is
recorded in status/rejected.json with the error and retried a day later, or as soon as the image's manifests
change. Nothing here deletes data on failure: a source that cannot be reached keeps its previous data and the
failure is recorded, as static-api did.
"""

from __future__ import annotations

import argparse
import datetime
import json
import logging
import os
import sys
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
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
from .sources.registry import base_layers
from .store import ImageRecord, Store, load_store, save_store

log = logging.getLogger(__name__)
Json = dict[str, Any]
Now = Callable[[], str]
Texts = dict[tuple[str, str, str], str | None]
"""(owner/name, ref, path) -> file text, None when the file does not exist."""

BASE_RETRY_SECONDS = 24 * 3600
"""How long a base image whose registry lookup failed waits before it is tried again."""
REJECTED_RETRY_SECONDS = 24 * 3600
"""How long a rejected release waits before it is tried again, unless its image's manifests change."""


def _now() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class IngestError(Exception):
    """A release that cannot be ingested; the message goes to status/rejected.json."""


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


MAX_CANDIDATE_BRANCHES = 30
"""Branches read when looking for a tag that no branch of its name publishes, so docker-mods-sized repos stay cheap."""


def fetch_manifests(gh: GitHub, repo: str, default_branch: str, texts: Texts | None = None) -> dict[str, Json]:
    """
    The manifest of every live branch: the default branch's image.yml, then one branch per tag in its
    `release.tags` whose own image.yml publishes that tag and names that branch. The branch is usually named after
    the tag, so that branch is read first; for a tag it does not publish (brave's `origin` lives on `borigin`) the
    other branches are listed and read, as control's fleet discovery does. Files in `texts` (from
    `prefetch_manifests`) are not fetched again.
    """

    def read(ref: str) -> str | None:
        key = (repo, ref, "image.yml")
        return texts[key] if texts is not None and key in texts else gh.file_text(repo, "image.yml", ref)

    def publishes(branch: str) -> Json | None:
        text = read(branch)
        if text is None:
            return None
        try:
            data = parse_manifest(text)
        except IngestError as e:
            log.warning("  %s@%s: %s", repo, branch, e)
            return None
        return data if data["release"]["branch"] == branch else None

    text = read(default_branch)
    if text is None:
        raise IngestError(f"no image.yml on {default_branch}")
    manifest = parse_manifest(text)
    manifests = {manifest["release"]["branch"]: manifest}
    wanted = [t for t in dict.fromkeys(_other_tags(manifest)) if t != manifest["release"]["tag"]]
    missing: list[str] = []
    for tag in wanted:
        data = publishes(tag)
        if data is not None and data["release"]["tag"] == tag:
            manifests[tag] = data
        else:
            missing.append(tag)
    if missing:
        names = [str(b["name"]) for b in gh.paginate(f"repos/{repo}/branches", max_pages=2)]
        for branch in [b for b in names if b not in manifests and b not in wanted][:MAX_CANDIDATE_BRANCHES]:
            data = publishes(branch)
            if data is not None and data["release"]["tag"] in missing:
                manifests[branch] = data
                missing.remove(data["release"]["tag"])
            if not missing:
                break
    if missing:
        log.info("  %s: no branch publishes %s; not live", repo, ", ".join(missing))
    return manifests


def _other_tags(manifest: Json) -> list[str]:
    return [str(entry["tag"]) for entry in manifest["release"].get("tags", [])]


def prefetch_manifests(gh: GitHub, repos: list[Json]) -> Texts:
    """
    Every image.yml a reconcile reads, in a few GraphQL requests instead of one REST request each: the default
    branch's of every repository, then those of the branches their `release.tags` name. Empty when GraphQL fails;
    `fetch_manifests` then reads each file over REST.
    """
    try:
        texts = gh.file_texts([(f"{ORG}/{r['name']}", r["default_branch"], "image.yml") for r in repos])
        others = []
        for (repo, _, path), text in list(texts.items()):
            try:
                manifest = parse_manifest(text) if text is not None else None
            except IngestError:
                continue
            if manifest:
                others += [(repo, tag, path) for tag in _other_tags(manifest) if tag != manifest["release"]["tag"]]
        texts.update(gh.file_texts(sorted(set(others))))
    except (httpx2.HTTPError, RuntimeError, KeyError, TypeError) as e:
        log.warning("reading manifests over GraphQL failed (%s); reading each one over REST instead", e)
        return {}
    return texts


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


def read_record(gh: GitHub, assets: dict[str, Json], bundle: Json, name: str) -> Json | None:
    """
    The release's record.json (CONVENTIONS §6), derived by the build itself, or None when the release has none or
    it does not fit this bundle; the hub then derives everything from the other assets, as for older releases.
    """
    asset = assets.get("record.json")
    if asset is None:
        return None
    try:
        derived = json.loads(gh.download(asset["url"]))
        validate("record", derived)
    except (json.JSONDecodeError, UnicodeDecodeError, ContractError, httpx2.HTTPError) as e:
        log.warning("  %s@%s: record.json unusable, deriving instead: %s", name, bundle["version"]["tag"], e)
        return None
    if derived["tag"] != bundle["version"]["tag"] or derived["image"] != name:
        log.warning(
            "  %s@%s: record.json is for %s@%s", name, bundle["version"]["tag"], derived["image"], derived["tag"]
        )
        return None
    for error in derived["errors"]:
        log.info("  %s@%s: the build could not derive: %s", name, bundle["version"]["tag"], error)
    result: Json = derived
    return result


def ingest_release(gh: GitHub, record: ImageRecord, release: Json, bases: dict[str, Json] | None = None) -> Json:
    """
    Downloads, validates and stores one release. Returns the bundle. Raises IngestError when it cannot.

    A release with a record.json needs two downloads: the build derived its package tables, diff, scan and base
    layers already. Whatever the record lacks comes from the other assets, derived here. The base layers it
    carries go into `bases` (data/bases/), so the registry is not asked for them.
    """
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
    derived = read_record(gh, assets, bundle, record.name) or {}

    layers: dict[str, list[Json]] = {}
    tests: dict[str, Json] = {}
    tables: dict[str, Json] = {}
    for arch in ARCHES:
        test_asset = assets.get(f"test.{arch}.json")
        try:
            if arch in derived.get("tests", {}):
                report = derived["tests"][arch]
            elif test_asset:
                report = json.loads(gh.download(test_asset["url"]))
            else:
                continue
            validate("test-report", report)
            tests[arch] = report
        except (json.JSONDecodeError, UnicodeDecodeError, ContractError) as e:
            log.warning("  %s@%s: test.%s.json unusable: %s", record.name, tag, arch, e)
    for arch in successful:
        layer_asset = assets.get(f"layers.{arch}.json")
        if arch in derived.get("layers", {}):
            layers[arch] = derived["layers"][arch]
        elif layer_asset:
            try:
                layers[arch] = json.loads(gh.download(layer_asset["url"]))
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                log.warning("  %s@%s: layers.%s.json unreadable: %s", record.name, tag, arch, e)
        package_asset = assets.get(f"packages.{arch}.json.gz")
        if arch in derived.get("packages", {}):
            tables[arch] = pkg.table(record.name, branch, release_tag, tag, arch, derived["packages"][arch])
        elif package_asset:
            try:
                rows = pkg.normalise_gz(gh.download(package_asset["url"]))
            except (OSError, ValueError) as e:
                log.warning("  %s@%s: packages.%s.json.gz unreadable: %s", record.name, tag, arch, e)
            else:
                tables[arch] = pkg.table(record.name, branch, release_tag, tag, arch, rows)
    if derived.get("vulns"):
        record.vulns[tag] = dict(derived["vulns"])
    base = derived.get("base")
    if bases is not None and base and base.get("digest") and base.get("platforms") and base["digest"] not in bases:
        bases[base["digest"]] = {**base, "fetched_at": derived["derived_at"]}

    previous = _previous(record, bundle)
    old_tables = record.packages.get(branch, {})
    old_packages = (
        {arch: t["packages"] for arch, t in old_tables.items()}
        if previous and old_tables and all(t["tag"] == previous["version"]["tag"] for t in old_tables.values())
        else None
    )
    new_packages = {arch: t["packages"] for arch, t in tables.items()} or None
    record.builds[tag] = bundle
    record.diffs[tag] = derived["diff"] if derived else diff_builds(bundle, previous, new_packages, old_packages)
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


def _age_seconds(then: str, now: str) -> float:
    try:
        start = datetime.datetime.fromisoformat(then.replace("Z", "+00:00"))
        return (datetime.datetime.fromisoformat(now.replace("Z", "+00:00")) - start).total_seconds()
    except ValueError:
        return float("inf")


def refresh_bases(store: Store, http: httpx2.Client, now: Now = _now) -> list[str]:
    """
    Fetches the layer digests of every base digest the held builds record and data/bases/ lacks. Returns the
    digests fetched. A registry failure is logged and recorded in status/bases.json, and that base is tried again
    after BASE_RETRY_SECONDS, so a registry that refuses costs one request a day instead of one every run.
    """
    fetched: list[str] = []
    failures: Json = store.status.setdefault("bases", {})
    images = {
        build["base"]["digest"]: build["base"]["image"]
        for record in store.images.values()
        for build in record.builds.values()
        if build.get("base", {}).get("digest")
    }
    for digest in sorted(set(failures) - store.base_digests()):
        failures.pop(digest)
    for digest in sorted(store.base_digests() - store.bases.keys()):
        image = images[digest]
        failed = failures.get(digest)
        if failed and failed.get("image") == image and _age_seconds(failed["checked_at"], now()) < BASE_RETRY_SECONDS:
            continue
        try:
            base = base_layers(http, image, digest)
        except (httpx2.HTTPError, KeyError, TypeError, ValueError) as e:
            log.warning("  ! base %s (%s): %s", image, digest[:19], e)
            failures[digest] = {"image": image, "checked_at": now(), "error": str(e).split("\n")[0]}
            continue
        if not base["platforms"]:
            log.warning("  ! base %s (%s): no linux platform in the manifest", image, digest[:19])
            failures[digest] = {"image": image, "checked_at": now(), "error": "no linux platform in the manifest"}
            continue
        failures.pop(digest, None)
        store.bases[digest] = {**base, "fetched_at": now()}
        fetched.append(digest)
        log.info(
            "  + base %s (%s): %s",
            image,
            digest[:19],
            ", ".join(f"{a} {len(p['layers'])}" for a, p in base["platforms"].items()),
        )
    return fetched


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


def ingest_repo(
    store: Store,
    gh: GitHub,
    repo: Json,
    now: Now,
    *,
    texts: Texts | None = None,
    releases: list[Json] | None = None,
) -> int:
    """
    Manifests of every live branch, then every pending release, for one image repository. `releases` is the
    repository's listing when the caller has it (without assets: each pending release is then read by tag);
    otherwise the releases are listed over REST. A release rejected less than REJECTED_RETRY_SECONDS ago is
    not tried again unless the manifests changed. Returns how many releases were tried.
    """
    name = image_name(repo["name"])
    full = f"{ORG}/{repo['name']}"
    record = store.record(name)
    manifests = fetch_manifests(gh, full, repo["default_branch"], texts)
    changed = manifests != record.manifests
    record.manifests = manifests
    rejected = store.status.get("rejected", {})

    def due(release: Json) -> bool:
        previous = rejected.get(f"{name}@{release['tag_name']}")
        return changed or previous is None or _age_seconds(previous["checked_at"], now()) >= REJECTED_RETRY_SECONDS

    tried = 0
    listing = releases if releases is not None else gh.releases(full)
    for release in [r for r in pending_releases(record, listing) if due(r)]:
        tried += 1
        try:
            if "assets" not in release:
                release = gh.release_by_tag(full, release["tag_name"])
            bundle = ingest_release(gh, record, release, store.bases)
        except (IngestError, httpx2.HTTPError) as e:
            _reject(store, record, release, str(e), now)
            continue
        _accept(store, record, release)
        log.info(
            "  + %s@%s (%s)", name, bundle["version"]["tag"], record.diffs[bundle["version"]["tag"]]["classification"]
        )
    rotate(record)
    return tried


def _set_status(store: Store, source: str, ok: bool, now: Now, error: str | None = None) -> None:
    previous = store.status["sources"].get(source, {})
    status = {"ok": ok, "checked_at": now(), "fetched_at": now() if ok else previous.get("fetched_at")}
    if error:
        status["error"] = error
    store.status["sources"][source] = {k: v for k, v in status.items() if v is not None}


def reconcile(store: Store, gh: GitHub, now: Now = _now, *, deep: bool = False) -> list[str]:
    """
    Every docker-* repository in the organisation: the manifests of every live branch and every release the hub
    does not hold yet. Every run of the hub does this; a dispatch's release is only a hint, because GitHub keeps
    one pending run per concurrency group and drops the older ones, so each run must find everything pending.

    Four or five GraphQL requests cover the organisation: the repositories, the newest 30 releases of each, and
    every image.yml. REST is only used for what is new (each pending release and its assets). `deep` lists every
    repository's releases over REST instead (up to 300 each), for a backfill. Repositories that fail keep their
    previous data. Returns the repositories whose releases were tried.
    """
    try:
        repos = [r for r in gh.org_repos(ORG) if is_image_repo(r["name"])]
    except (httpx2.HTTPError, RuntimeError) as e:
        _set_status(store, "manifests", False, now, f"listing repositories: {e}")
        _set_status(store, "releases", False, now, f"listing repositories: {e}")
        return []
    index: dict[str, list[Json]] | None = None
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending_listing = None if deep else pool.submit(gh.org_releases, ORG)
        texts = prefetch_manifests(gh, repos)
        try:
            index = pending_listing.result() if pending_listing else None
        except (httpx2.HTTPError, RuntimeError, KeyError, TypeError) as e:
            log.warning("listing releases over GraphQL failed (%s); listing each repository's over REST instead", e)
    tried: list[str] = []
    failures: list[str] = []
    for repo in repos:
        try:
            listing = index.get(repo["name"], []) if index is not None else None
            if ingest_repo(store, gh, repo, now, texts=texts, releases=listing):
                tried.append(f"{ORG}/{repo['name']}")
        except (IngestError, httpx2.HTTPError) as e:
            failures.append(f"{repo['name']}: {e}")
            log.warning("  ! %s: %s (keeping previous data)", repo["name"], e)
    names = {image_name(r["name"]) for r in repos}
    for gone in sorted(set(store.images) - names):
        log.info("  - %s: repository no longer in the organisation; removing its data", gone)
        store.images.pop(gone)
    refresh_bases(store, gh.http, now)
    error = "; ".join(failures) if failures else None
    _set_status(store, "manifests", not failures, now, error)
    _set_status(store, "releases", not failures, now, error)
    log.info("reconcile: %d of %d image repositories had something new", len(tried), len(repos))
    return tried


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
        ingest_release(gh, record, release, store.bases)
    except (IngestError, httpx2.HTTPError) as e:
        _reject(store, record, release, str(e), now)
        return False
    _accept(store, record, release)
    rotate(record)
    refresh_bases(store, gh.http, now)
    _set_status(store, "releases", True, now)
    return True


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("httpx2").setLevel(logging.WARNING)
    parser = argparse.ArgumentParser(description="Ingest manifests and build bundles into data/.")
    parser.add_argument("--reconcile", action="store_true", help="every repository and release in the organisation")
    parser.add_argument("--deep", action="store_true", help="with --reconcile: list every release over REST (backfill)")
    parser.add_argument("--pending", action="store_true", help="the same as --reconcile (kept for older callers)")
    parser.add_argument("--repo", help="owner/name of one image repository")
    parser.add_argument("--tag", help="the release tag to ingest from --repo")
    args = parser.parse_args(argv)
    if not args.reconcile and not args.pending and not (args.repo and args.tag):
        parser.error("use --reconcile [--deep], or --repo owner/name --tag x")
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        log.warning("GITHUB_TOKEN is not set; anonymous GitHub requests are rate limited to 60 an hour")
    store = load_store(DATA_DIR)
    gh = GitHub(client(), token)
    if args.reconcile or args.pending:
        reconcile(store, gh, deep=args.deep)
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
