"""Builds the content of each response from the fleet. Pure, so each endpoint is tested without HTTP."""

from __future__ import annotations

import datetime
from collections import Counter, defaultdict
from typing import Any

from builder.derive import documents
from builder.manifest import build_context
from builder.render import render_all

from .config import STORE_REPOS, WEBSITE, build_pages, release_download, site_build
from .dates import parse_iso
from .fleet import Fleet
from .generate import kubernetes, proxy, proxy_refs, quadlet
from .generate.common import ImageInput
from .models import (
    CHANGELOG_LIMIT,
    V1_CHANGELOG_ENTRIES,
    BaseDigest,
    BasesData,
    BaseUsage,
    BuildLinks,
    BuildReport,
    BuildsData,
    BuildSummary,
    BuildTestsData,
    Bundle,
    Category,
    ChangelogEntry,
    Diff,
    DocsData,
    DocSection,
    HistoryEntry,
    Image,
    ImageDetail,
    ImageModsData,
    ImagesData,
    ImagesResponse,
    LayersData,
    Mod,
    ModsData,
    Package,
    PackageData,
    PackageHolder,
    PackageIndexEntry,
    PackagesData,
    ProotAppsData,
    ProxyData,
    Repository,
    StaleImage,
    StalenessData,
    Stats,
    Status,
    StoreEntry,
    TestArchSummary,
    VulnerabilitySummary,
)
from .packages import slug, version_key
from .store import ImageRecord

Json = dict[str, Any]
_V1_FIELDS = Image.model_fields.keys() - {"changelog", "config"}

# ---------------------------------------------------------------------------------------------------
# v1 and the static-api endpoints


def to_v1_image(image: ImageDetail, include_config: bool) -> Image:
    """The v1 view of an image: the original fields only, three changelog entries, config on request."""
    return Image(
        **{key: getattr(image, key) for key in _V1_FIELDS},
        changelog=image.changelog[:V1_CHANGELOG_ENTRIES] if image.changelog is not None else None,
        config=image.config if include_config else None,
    )


def images_response(fleet: Fleet, include_config: bool = False, include_deprecated: bool = False) -> ImagesResponse:
    # Like the original API, the list holds applications only: base images and tools are in the catalog.
    images = [i for i in fleet.images if i.kind == "app"] if include_deprecated else fleet.apps
    linuxserver = [to_v1_image(i, include_config) for i in images]
    return ImagesResponse(
        status="OK", last_updated=fleet.last_updated, data=ImagesData(repositories=Repository(linuxserver=linuxserver))
    )


def slugify(name: str) -> str:
    return "-".join("".join(c if c.isalnum() else " " for c in name.lower()).split())


def categories(fleet: Fleet) -> list[Category]:
    """Categories of current applications, most populated first."""
    by_name: defaultdict[str, list[str]] = defaultdict(list)
    for image in fleet.apps:
        for category in image.categories:
            by_name[category].append(image.name)
    found = [Category(name=n, slug=slugify(n), count=len(i), images=sorted(i)) for n, i in by_name.items()]
    return sorted(found, key=lambda c: (-c.count, c.name.casefold()))


def stats(fleet: Fleet) -> Stats:
    images = fleet.apps
    updated = parse_iso(fleet.updated_at)
    week_before = updated - datetime.timedelta(days=7) if updated else None

    def recent(image: ImageDetail) -> bool:
        released = parse_iso(image.version_timestamp)
        return bool(released and week_before and released >= week_before)

    first_dates = sorted(i.initial_date for i in images if i.initial_date)
    return Stats(
        images=len(images),
        base_images=sum(1 for i in fleet.current if i.kind == "base"),
        tools=sum(1 for i in fleet.current if i.kind == "tool"),
        deprecated=len(fleet.images) - len(fleet.current),
        stars=sum(i.stars for i in images),
        builds=sum(len(r.builds) for r in fleet.store.images.values()),
        architectures=dict(Counter(arch for i in images for arch in dict.fromkeys(a.arch for a in i.architectures))),
        readonly_supported=sum(1 for i in images if i.config.readonly_supported),
        nonroot_supported=sum(1 for i in images if i.config.nonroot_supported),
        updated_last_7_days=sum(1 for i in images if recent(i)),
        categories=len({c for i in images for c in i.categories}),
        first_release=first_dates[0] if first_dates else None,
    )


def recent_changelog(fleet: Fleet) -> list[ChangelogEntry]:
    """The most recent changelog entries across current images: newest first, then by image name."""
    entries = [(c.date, image.name, c.desc) for image in fleet.current for c in image.changelog or []]
    entries.sort(key=lambda e: e[1])
    entries.sort(key=lambda e: e[0], reverse=True)
    return [ChangelogEntry(image=name, date=date, desc=desc) for date, name, desc in entries[:CHANGELOG_LIMIT]]


def status(fleet: Fleet) -> Status:
    current = len(fleet.current)
    return Status(
        health=fleet.health,
        images=current,
        deprecated=len(fleet.images) - current,
        sources=fleet.sources,
        rejected=fleet.rejected,
    )


# ---------------------------------------------------------------------------------------------------
# Builds


def is_newest(record: ImageRecord, build: Json) -> bool:
    """Whether a build is the newest of its branch the hub holds (only that one has a package table)."""
    return bool(record.latest.get(build["branch"], {}).get("tag") == build["version"]["tag"])


RUN_FILES = {"run_json": "run.json", "logs_zip": "logs.zip"}
"""The Release assets control attaches after a run: its structured record and the run's masked log archive."""


def _asset_urls(build: Json) -> dict[str, str]:
    return {a["name"]: str(a["url"]) for a in build.get("assets", []) if a.get("url")}


def _asset_names(build: Json) -> set[str]:
    return {str(a["name"]) for a in build.get("assets", [])}


def _build_links(fleet: Fleet, record: ImageRecord, build: Json) -> BuildLinks:
    """
    The API's own documents, then the heavy files on the image repository's Pages (`config.repo_pages`), which keeps
    the same newest builds the hub does, the build's own vulnerability scan among them. Release assets appear only as
    download links: they send no CORS headers. The report page is the build's page on the website.
    """
    tag, branch, repository = build["version"]["tag"], build["branch"], build["repository"]
    api = f"{fleet.site.api_root}/api/v1/catalog/{record.name}/builds/{tag}"
    pages = build_pages(repository, tag)
    has_table = {arch for arch, t in record.packages.get(branch, {}).items() if t["tag"] == tag}
    names = _asset_names(build)
    release = next((h.get("release_url") for h in record.history.get(branch, []) if h["tag"] == tag), None)

    def on_pages(kind: str) -> dict[str, str]:
        arches = {n[len(kind) + 1 : -8] for n in names if n.startswith(f"{kind}.") and n.endswith(".json.gz")}
        return {arch: f"{pages}{kind}.{arch}.json.gz" for arch in sorted(arches)}

    return BuildLinks(
        build=f"{api}.json",
        diff=f"{api}/diff.json",
        layers={arch: f"{api}/layers.{arch}.json" for arch in sorted(record.layers.get(tag, {}))},
        packages={arch: f"{api}/packages.{arch}.json" for arch in sorted(has_table)},
        release=release,
        pages=pages,
        files=on_pages("files"),
        sbom=on_pages("packages"),
        **{key: release_download(repository, tag, name) for key, name in RUN_FILES.items()},
        test_report=site_build(record.name, tag),
        tests=f"{api}/tests.json" if record.tests.get(tag) else None,
        report=f"{api}/report.json",
        vulns=f"{pages}vulns.json" if record.vulns.get(tag) else None,
    )


def published_tags(build: Json) -> list[str]:
    """
    The tags a build pushed: build.json `published.tags` (CONVENTIONS §6), else, for a release made before that field,
    `version.tags`, which a live release published in full (its Release exists only once they were). Never a registry
    listing: a build's tags are fixed when it publishes.
    """
    published = build.get("published") or {}
    tags = published.get("tags") if isinstance(published, dict) else None
    if isinstance(tags, list) and tags:
        return [str(t) for t in tags]
    return [str(t) for t in (build.get("version") or {}).get("tags") or []]


def build_summary(fleet: Fleet, record: ImageRecord, build: Json) -> BuildSummary:
    tag = build["version"]["tag"]
    diff = record.diffs.get(tag)
    return BuildSummary(
        tag=tag,
        branch=build["branch"],
        release_tag=build["version"].get("release_tag"),
        upstream_version=build["version"]["upstream"],
        semver=build["version"].get("semver"),
        ls_build=build["version"]["ls_build"],
        created=build["created"],
        reason=build["reason"],
        commit=build["commit"],
        test_success=build["test"]["success"] if build["test"].get("enabled", True) else None,
        base=build["base"],
        platforms=build["platforms"],
        tags=published_tags(build),
        classification=diff["classification"] if diff else None,
        vulnerabilities=vuln_summary(record, tag),
        links=_build_links(fleet, record, build),
    )


def _history_entry(record: ImageRecord, entry: Json) -> HistoryEntry:
    """A release of the branch, with the run that built it and download links to control's run record and logs."""
    build = record.builds.get(entry["tag"]) or {}
    run_url = entry.get("run_url") or (build.get("workflow") or {}).get("run_url")
    release = str(entry.get("release_url") or "")
    links = {}
    if "/releases/tag/" in release:
        base = release.replace("/releases/tag/", "/releases/download/", 1)
        links = {key: f"{base}/{name}" for key, name in RUN_FILES.items()}
    return HistoryEntry.model_validate({**entry, "run_url": run_url, **links})


def builds(fleet: Fleet, record: ImageRecord) -> BuildsData:
    return BuildsData(
        image=record.name,
        builds=[build_summary(fleet, record, b) for b in record.sorted_builds()],
        history={
            branch: [_history_entry(record, h) for h in entries] for branch, entries in sorted(record.history.items())
        },
    )


def bundle(record: ImageRecord, tag: str) -> Bundle | None:
    build = record.builds.get(tag)
    return Bundle.model_validate(build) if build else None


def diff(record: ImageRecord, tag: str) -> Diff | None:
    data = record.diffs.get(tag)
    return Diff.model_validate(data) if data else None


def layers(record: ImageRecord, tag: str, arch: str, bases: dict[str, Json] | None = None) -> LayersData | None:
    """The layer table with `from_base` from the base's registry manifest and `dockerfile_lines` from the Dockerfile
    (`builder.derive.documents.layers`, which the copies on the repository's Pages use too)."""
    per_arch = record.layers.get(tag, {})
    build = record.builds.get(tag)
    if arch not in per_arch or build is None:
        return None
    base = (bases or {}).get(build.get("base", {}).get("digest") or "")
    doc = documents.layers({**build, "image": record.name}, arch, per_arch[arch], base)
    return LayersData.model_validate(doc)


def _test_summaries(record: ImageRecord, build: Json) -> dict[str, TestArchSummary]:
    reports = record.tests.get(build["version"]["tag"], {})
    pages = build_pages(build["repository"], build["version"]["tag"])
    summaries = documents.test_summaries(build, reports, pages)
    return {arch: TestArchSummary.model_validate(summary) for arch, summary in summaries.items()}


def tests(fleet: Fleet, record: ImageRecord, tag: str) -> BuildTestsData | None:
    """The harness reports per architecture with a summary (`builder.derive.documents.tests`); None without one."""
    build = record.builds.get(tag)
    reports = record.tests.get(tag)
    if build is None or not reports:
        return None
    doc = documents.tests({**build, "image": record.name}, reports, build_pages(build["repository"], tag), WEBSITE)
    return BuildTestsData.model_validate(doc) if doc else None


def test_routes(fleet: Fleet) -> list[tuple[str, str]]:
    """(image, tag) for every build with a harness report."""
    return [
        (name, tag)
        for name, record in sorted(fleet.store.images.items())
        for tag in sorted(record.tests)
        if tag in record.builds
    ]


def vuln_summary(record: ImageRecord, tag: str) -> VulnerabilitySummary | None:
    """The counts of the build's own scan, made when it was built (its vulns.json is on the repository's Pages)."""
    counts = record.vulns.get(tag)
    return VulnerabilitySummary.model_validate(counts["summary"]) if counts else None


build_result = documents.build_result
"""`success`, `failure` or `partial` over every platform and the test outcome."""


def report(fleet: Fleet, record: ImageRecord, tag: str) -> BuildReport | None:
    """Everything a build page shows, in one document (`builder.derive.documents.report`), with the hub's links."""
    build = record.builds.get(tag)
    if build is None:
        return None
    doc = documents.report(
        {**build, "image": record.name},
        diff=record.diffs.get(tag),
        reports=record.tests.get(tag, {}),
        build_links=_build_links(fleet, record, build).model_dump(exclude_none=True),
        site=WEBSITE,
        is_newest=is_newest(record, build),
    )
    return BuildReport.model_validate(doc)


def packages_table(record: ImageRecord, tag: str, arch: str) -> PackagesData | None:
    for tables in record.packages.values():
        table = tables.get(arch)
        if table and table["tag"] == tag:
            rows = [Package.model_validate(r) for r in table["packages"]]
            return PackagesData(image=record.name, tag=tag, arch=arch, count=len(rows), packages=rows)
    return None


def package_routes(fleet: Fleet) -> list[tuple[str, str, str]]:
    """(image, tag, arch) for every stored package table."""
    return [
        (name, table["tag"], arch)
        for name, record in sorted(fleet.store.images.items())
        for tables in record.packages.values()
        for arch, table in sorted(tables.items())
        if table["tag"] in record.builds
    ]


def layer_routes(fleet: Fleet) -> list[tuple[str, str, str]]:
    return [
        (name, tag, arch)
        for name, record in sorted(fleet.store.images.items())
        for tag, per_arch in sorted(record.layers.items())
        for arch in sorted(per_arch)
        if tag in record.builds
    ]


# ---------------------------------------------------------------------------------------------------
# Mods


def mods(fleet: Fleet) -> ModsData:
    return ModsData(source=str(fleet.store.mods.get("source", "none")), mods=fleet.mods)


def image_mods(fleet: Fleet, name: str) -> ImageModsData:
    """The image's own mods, then the universal mods curated for it, then every other universal mod."""
    own = [m for m in fleet.mods if m.target == name or (name in m.applies_to and m.target != "universal")]
    universal = [m for m in fleet.mods if m.target == "universal"]
    curated = [m for m in universal if name in m.applies_to]
    return ImageModsData(image=name, mods=own + curated + [m for m in universal if m not in curated])


def proot_apps(fleet: Fleet) -> ProotAppsData:
    data = fleet.store.proot_apps
    return ProotAppsData.model_validate(
        {"source": data.get("source", "none"), "cli": data.get("cli"), "apps": data.get("apps", [])}
    )


# ---------------------------------------------------------------------------------------------------
# Generated per-image documents


def _input(fleet: Fleet, name: str) -> ImageInput | None:
    record = fleet.record(name)
    if record is None or record.manifest is None:
        return None
    observed = fleet.store.observed.get("images", {}).get(name, {})
    return ImageInput(name, record, record.manifest, build_context(record.manifest, fleet.settings), observed)


def proxy_data(fleet: Fleet, name: str) -> ProxyData | None:
    image = _input(fleet, name)
    if image is None or image.kind != "app" or not image.manifest.get("proxy"):
        return None
    block = image.manifest["proxy"]
    return ProxyData(
        image=name,
        port=int(block["port"]),
        scheme=str(block.get("scheme", "http")),
        subdomain=proxy.subdomain(image) if block.get("subdomain", True) else None,
        subfolder=proxy.subfolder(image),
        caddy=proxy_refs.caddy(image),
        traefik=proxy_refs.traefik(image),
        base_url_note=block.get("subfolder", {}).get("base_url_note"),
        config=block,
    )


def doc_sections(markdown: str) -> list[DocSection]:
    """`##` sections of a Markdown document, in order; headings inside fenced code are text. The part before the
    first `##` (title, badges, logo) is not a section."""
    sections: list[DocSection] = []
    title: str | None = None
    body: list[str] = []
    fence: str | None = None

    def close() -> None:
        if title is not None:
            sections.append(DocSection(id=_slug(title), title=title, markdown="\n".join(body).strip("\n") + "\n"))

    for line in markdown.splitlines():
        stripped = line.lstrip()
        if fence:
            if stripped.startswith(fence):
                fence = None
        elif stripped.startswith(("```", "~~~")):
            fence = stripped[:3]
        elif line.startswith("## "):
            close()
            title, body = line[3:].strip(), []
            continue
        body.append(line)
    close()
    return sections


def _slug(title: str) -> str:
    return "-".join("".join(c if c.isalnum() else " " for c in title.lower()).split())


def docs_data(fleet: Fleet, name: str) -> DocsData | None:
    record = fleet.record(name)
    if record is None or record.manifest is None:
        return None
    readme = render_all(record.manifest, fleet.settings)["README.md"]
    return DocsData(image=name, sections=doc_sections(readme))


def kubernetes_yaml(fleet: Fleet, name: str) -> str | None:
    image = _input(fleet, name)
    if image is None or image.kind != "app":
        return None
    if not image.manifest.get("publish", {}).get("kubernetes", {}).get("enabled", True):
        return None
    return kubernetes.render(image)


def quadlet_unit(fleet: Fleet, name: str) -> str | None:
    image = _input(fleet, name)
    if image is None or image.kind != "app" or not image.manifest.get("publish", {}).get("quadlet", True):
        return None
    return quadlet.render(image)


def names_with(fleet: Fleet, kind: str) -> list[str]:
    """Image names that have a given generated document (proxy, kubernetes, quadlet)."""
    out = []
    for image in fleet.images:
        if image.kind != "app":
            continue
        manifest = (fleet.record(image.name) or ImageRecord(image.name)).manifest or {}
        publish = manifest.get("publish", {})
        has = {
            "proxy": bool(manifest.get("proxy")),
            "kubernetes": bool(publish.get("kubernetes", {}).get("enabled", True)),
            "quadlet": bool(publish.get("quadlet", True)),
        }
        if has[kind]:
            out.append(image.name)
    return out


# ---------------------------------------------------------------------------------------------------
# Packages across the fleet


def _holders(fleet: Fleet) -> dict[str, list[PackageHolder]]:
    """Every package row of the fleet by package name. Built once per fleet: the static build asks for it once per
    package page, and rebuilding it each time made the build quadratic (minutes at a few thousand packages)."""
    cached: dict[str, list[PackageHolder]] | None = fleet.__dict__.get("_package_holders")
    if cached is not None:
        return cached
    by_name: dict[str, list[PackageHolder]] = defaultdict(list)
    for name, record in sorted(fleet.store.images.items()):
        for branch, tables in sorted(record.packages.items()):
            for arch, table in sorted(tables.items()):
                for row in table["packages"]:
                    by_name[row["name"]].append(
                        PackageHolder(
                            image=name,
                            tag=table["tag"],
                            branch=branch,
                            arch=arch,
                            version=row["version"],
                            type=row["type"],
                            purl=row.get("purl"),
                        )
                    )
    # Fleet is frozen and its data never changes once loaded; __dict__ is the one place to keep the result.
    fleet.__dict__["_package_holders"] = by_name
    return by_name


def _names_by_slug(fleet: Fleet) -> dict[str, str]:
    cached: dict[str, str] | None = fleet.__dict__.get("_package_slugs")
    if cached is None:
        cached = {slug(name): name for name in _holders(fleet)}
        fleet.__dict__["_package_slugs"] = cached
    return cached


def package_index(fleet: Fleet) -> list[PackageIndexEntry]:
    entries = []
    for name, holders in sorted(_holders(fleet).items(), key=lambda kv: kv[0].casefold()):
        entries.append(
            PackageIndexEntry(
                name=name,
                slug=slug(name),
                types=sorted({h.type for h in holders}),
                images=len({h.image for h in holders}),
            )
        )
    return entries


def package_detail(fleet: Fleet, package_slug: str) -> PackageData | None:
    name = _names_by_slug(fleet).get(package_slug)
    if name is None:
        return None
    holders = _holders(fleet)[name]
    return PackageData(
        name=name,
        slug=package_slug,
        types=sorted({h.type for h in holders}),
        versions=sorted({h.version for h in holders}, key=version_key, reverse=True),
        images=sorted({h.image for h in holders}),
        holders=holders,
    )


def package_slugs(fleet: Fleet) -> list[str]:
    return sorted(_names_by_slug(fleet))


# ---------------------------------------------------------------------------------------------------
# Fleet: bases and staleness


def _newest_builds(fleet: Fleet) -> list[tuple[ImageRecord, Json]]:
    out = []
    for record in fleet.store.images.values():
        for branch in record.manifests:
            build = record.latest_build(branch)
            if build:
                out.append((record, build))
    return out


def bases(fleet: Fleet) -> BasesData:
    usage: dict[str, Json] = {}
    for record in fleet.store.images.values():
        for build in record.builds.values():
            ref = build["base"]["image"]
            entry = usage.setdefault(ref, {"family": build["base"]["family"], "digests": {}, "images": set()})
            digest = build["base"].get("digest")
            if digest:
                seen = entry["digests"].setdefault(
                    digest, {"first": build["created"], "last": build["created"], "images": set()}
                )
                seen["first"] = min(seen["first"], build["created"])
                seen["last"] = max(seen["last"], build["created"])
                seen["images"].add(record.name)
    for record, build in _newest_builds(fleet):
        usage[build["base"]["image"]]["images"].add(record.name)
    out = []
    for ref in sorted(usage):
        entry = usage[ref]
        digests = sorted(entry["digests"].items(), key=lambda kv: kv[1]["first"], reverse=True)
        out.append(
            BaseUsage(
                image=ref,
                family=entry["family"],
                images=sorted(entry["images"]),
                newest_digest=digests[0][0] if digests else None,
                newest_seen=digests[0][1]["first"] if digests else None,
                digests=[
                    BaseDigest(digest=d, first_seen=v["first"], last_seen=v["last"], images=sorted(v["images"]))
                    for d, v in digests
                ],
            )
        )
    return BasesData(bases=out)


def _base_releases(fleet: Fleet) -> dict[str, str]:
    """Newest build time per base image reference, when the base image itself is in the fleet (baseimage-*)."""
    out: dict[str, str] = {}
    for record in fleet.store.images.values():
        if not record.name.startswith("baseimage-"):
            continue
        for build in record.builds.values():
            for tag in published_tags(build) or [build["version"]["tag"]]:
                ref = f"{fleet.settings.registry}/{fleet.settings.org}/{record.name}:{tag}"
                out[ref] = max(out.get(ref, ""), build["created"])
    return out


def staleness(fleet: Fleet) -> StalenessData:
    """Newest builds whose base was seen newer elsewhere: a later digest in another build, or a later base release."""
    newest = {b.image: b for b in bases(fleet).bases}
    base_releases = _base_releases(fleet)
    stale = []
    checked = 0
    for record, build in _newest_builds(fleet):
        checked += 1
        ref = build["base"]["image"]
        usage = newest.get(ref)
        digest = build["base"].get("digest")
        if (
            usage
            and usage.newest_digest
            and digest
            and usage.newest_digest != digest
            and (usage.newest_seen or "") > build["created"]
        ):
            stale.append(
                StaleImage(
                    image=record.name,
                    branch=build["branch"],
                    tag=build["version"]["tag"],
                    built=build["created"],
                    base=ref,
                    base_digest=digest,
                    newest_base_digest=usage.newest_digest,
                    newest_base_built=usage.newest_seen or "",
                    reason="another image was built against a newer digest of the same base",
                )
            )
            continue
        released = base_releases.get(ref)
        if released and released > build["created"]:
            stale.append(
                StaleImage(
                    image=record.name,
                    branch=build["branch"],
                    tag=build["version"]["tag"],
                    built=build["created"],
                    base=ref,
                    base_digest=digest,
                    newest_base_digest=None,
                    newest_base_built=released,
                    reason="the base image released after this build",
                )
            )
    stale.sort(key=lambda s: (s.image, s.branch))
    return StalenessData(stale=stale, checked=checked)


# ---------------------------------------------------------------------------------------------------
# Stores


def stores_index(fleet: Fleet) -> list[StoreEntry]:
    """The app stores, one import URL each. Per-image deployment files (Kubernetes, quadlets, SWAG proxy confs) are
    not stores: image pages link them from /stores/<platform>/<name>.*."""
    root = fleet.site.stores_root
    return [
        StoreEntry(
            platform="unraid",
            name="Unraid templates",
            url=f"https://github.com/{STORE_REPOS['unraid']}",
            how_to="One template XML per image at the repository root; deprecated images are in deprecated/.",
        ),
        StoreEntry(
            platform="portainer",
            name="Portainer app templates",
            url=f"{root}/portainer/templates.json",
            how_to="Portainer > Settings > App Templates > URL.",
        ),
        StoreEntry(
            platform="casaos",
            name="CasaOS app store",
            url=f"{root}/casaos/linuxserver.zip",
            how_to="CasaOS > App Store > More apps > Add source.",
        ),
        StoreEntry(
            platform="umbrel",
            name="Umbrel community app store",
            url=f"https://github.com/{STORE_REPOS['umbrel']}",
            how_to="Umbrel > App Store > Community App Stores > add this repository URL.",
        ),
        StoreEntry(
            platform="runtipi",
            name="Runtipi app store",
            url=f"https://github.com/{STORE_REPOS['runtipi']}",
            how_to="Runtipi > Settings > App Stores > Add App Store > this repository URL.",
        ),
        StoreEntry(
            platform="cosmos",
            name="Cosmos Cloud market",
            url=f"{root}/cosmos/index.json",
            how_to="Cosmos > Market > Sources > add the URL.",
        ),
        StoreEntry(
            platform="arcane",
            name="Arcane template registry",
            url=f"{root}/arcane/registry.json",
            how_to="Arcane > Customization > Templates > Add Registry > the URL.",
        ),
    ]


def mod_for(fleet: Fleet, name: str) -> list[Mod]:
    return image_mods(fleet, name).mods
