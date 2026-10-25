"""Builds the content of each response from the fleet. Pure, so each endpoint is tested without HTTP."""

from __future__ import annotations

import datetime
from collections import Counter, defaultdict
from typing import Any, Literal

from builder.manifest import build_context
from builder.render import render_all

from .config import STORE_REPOS
from .dates import parse_iso
from .fleet import Fleet
from .generate import kubernetes, proxy, quadlet
from .generate.common import ImageInput
from .layers import annotate
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
    BuildVulnsData,
    Bundle,
    Category,
    ChangelogEntry,
    Diff,
    DiffSummary,
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
    ProxyData,
    ReportLinks,
    Repository,
    StaleImage,
    StalenessData,
    Stats,
    Status,
    StoreEntry,
    TestArchSummary,
    TestReport,
    VulnerabilityMatch,
    VulnerabilitySummary,
)
from .packages import slug, version_key
from .store import ImageRecord
from .vulns import CAVEATS, merge, summarise

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
    images = fleet.images if include_deprecated else fleet.current
    linuxserver = [to_v1_image(i, include_config) for i in images]
    return ImagesResponse(
        status="OK", last_updated=fleet.last_updated, data=ImagesData(repositories=Repository(linuxserver=linuxserver))
    )


def slugify(name: str) -> str:
    return "-".join("".join(c if c.isalnum() else " " for c in name.lower()).split())


def categories(fleet: Fleet) -> list[Category]:
    """Categories of current images, most populated first."""
    by_name: defaultdict[str, list[str]] = defaultdict(list)
    for image in fleet.current:
        for category in image.categories:
            by_name[category].append(image.name)
    found = [Category(name=n, slug=slugify(n), count=len(i), images=sorted(i)) for n, i in by_name.items()]
    return sorted(found, key=lambda c: (-c.count, c.name.casefold()))


def stats(fleet: Fleet) -> Stats:
    images = fleet.current
    updated = parse_iso(fleet.updated_at)
    week_before = updated - datetime.timedelta(days=7) if updated else None

    def recent(image: ImageDetail) -> bool:
        released = parse_iso(image.version_timestamp)
        return bool(released and week_before and released >= week_before)

    first_dates = sorted(i.initial_date for i in images if i.initial_date)
    return Stats(
        images=len(images),
        deprecated=len(fleet.images) - len(images),
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
    """Whether a build is the newest of its branch the hub holds (only then are its heavy assets copied)."""
    return bool(record.latest.get(build["branch"], {}).get("tag") == build["version"]["tag"])


def _asset_urls(build: Json) -> dict[str, str]:
    return {a["name"]: str(a["url"]) for a in build.get("assets", []) if a.get("url")}


def _build_links(fleet: Fleet, record: ImageRecord, build: Json) -> BuildLinks:
    tag, branch = build["version"]["tag"], build["branch"]
    api = f"{fleet.site.api_root}/api/v1/catalog/{record.name}/builds/{tag}"
    page = f"{fleet.site.api_root}/builds/{record.name}/{tag}/"
    has_table = {arch for arch, t in record.packages.get(branch, {}).items() if t["tag"] == tag}
    assets = _asset_urls(build)
    release = next((h.get("release_url") for h in record.history.get(branch, []) if h["tag"] == tag), None)
    on_release = {a[6:-8]: url for a, url in assets.items() if a.startswith("files.") and a.endswith(".json.gz")}
    # The report generator copies files.<arch>.json.gz next to the page for the newest build of each branch.
    copied = is_newest(record, build)
    return BuildLinks(
        build=f"{api}.json",
        diff=f"{api}/diff.json",
        layers={arch: f"{api}/layers.{arch}.json" for arch in sorted(record.layers.get(tag, {}))},
        packages={arch: f"{api}/packages.{arch}.json" for arch in sorted(has_table)},
        release=release,
        files={arch: f"{page}files.{arch}.json.gz" if copied else url for arch, url in sorted(on_release.items())},
        files_release=dict(sorted(on_release.items())),
        test_report=page,
        tests=f"{api}/tests.json" if record.tests.get(tag) else None,
        report=f"{api}/report.json",
        vulns=f"{api}/vulns.json" if record.vulns.get(tag) else None,
    )


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
        classification=diff["classification"] if diff else None,
        vulnerabilities=vuln_summary(record, tag),
        links=_build_links(fleet, record, build),
    )


def builds(fleet: Fleet, record: ImageRecord) -> BuildsData:
    return BuildsData(
        image=record.name,
        builds=[build_summary(fleet, record, b) for b in record.sorted_builds()],
        history={
            branch: [HistoryEntry.model_validate(h) for h in entries]
            for branch, entries in sorted(record.history.items())
        },
    )


def bundle(record: ImageRecord, tag: str) -> Bundle | None:
    build = record.builds.get(tag)
    return Bundle.model_validate(build) if build else None


def diff(record: ImageRecord, tag: str) -> Diff | None:
    data = record.diffs.get(tag)
    return Diff.model_validate(data) if data else None


def layers(record: ImageRecord, tag: str, arch: str, bases: dict[str, Json] | None = None) -> LayersData | None:
    """The layer table with `from_base` from the base's registry manifest and `dockerfile_lines` from the Dockerfile."""
    per_arch = record.layers.get(tag, {})
    build = record.builds.get(tag)
    if arch not in per_arch or build is None:
        return None
    base = (bases or {}).get(build.get("base", {}).get("digest") or "")
    annotated, meta = annotate(per_arch[arch], build.get("dockerfile", {}).get(arch), base, arch)
    return LayersData(image=record.name, tag=tag, arch=arch, layers=annotated, **meta)


def _test_summary(fleet: Fleet, record: ImageRecord, build: Json, arch: str, report: Json) -> TestArchSummary:
    tag = build["version"]["tag"]
    runtime = report.get("runtime") or {}
    cases = report.get("tests") or []
    failed = [c["name"] for c in cases if str(c.get("status", "")).upper() not in ("PASS", "SKIP")]
    ports = [f"{p}/tcp" for p in runtime.get("listening_tcp") or []] + [
        f"{p}/udp" for p in runtime.get("listening_udp") or []
    ]
    has_html = bool((report.get("files") or {}).get("html"))
    return TestArchSummary(
        success=bool(report.get("success")),
        passed=sum(1 for c in cases if str(c.get("status", "")).upper() == "PASS"),
        failed=len(failed),
        total=len(cases),
        failed_tests=failed,
        startup_seconds=report.get("startup_seconds"),
        listening_ports=ports,
        warnings=len(report.get("warnings") or {}),
        rss_bytes=runtime.get("rss_bytes"),
        pids=runtime.get("pids"),
        report_page=f"{fleet.site.api_root}/builds/{record.name}/{tag}/{arch}/index.html" if has_html else None,
        tarball=_asset_urls(build).get(f"test.{arch}.tar.gz"),
    )


def _test_summaries(fleet: Fleet, record: ImageRecord, build: Json) -> dict[str, TestArchSummary]:
    reports = record.tests.get(build["version"]["tag"], {})
    return {arch: _test_summary(fleet, record, build, arch, reports[arch]) for arch in sorted(reports)}


def tests(fleet: Fleet, record: ImageRecord, tag: str) -> BuildTestsData | None:
    """The harness reports per architecture with a summary; None when the build has no report."""
    build = record.builds.get(tag)
    reports = record.tests.get(tag)
    if build is None or not reports:
        return None
    enabled = bool(build["test"].get("enabled", True))
    return BuildTestsData(
        image=record.name,
        tag=tag,
        enabled=enabled,
        success=build["test"]["success"] if enabled else None,
        report_url=f"{fleet.site.api_root}/builds/{record.name}/{tag}/",
        summary=_test_summaries(fleet, record, build),
        reports={arch: TestReport.model_validate(reports[arch]) for arch in sorted(reports)},
    )


def test_routes(fleet: Fleet) -> list[tuple[str, str]]:
    """(image, tag) for every build with a harness report."""
    return [
        (name, tag)
        for name, record in sorted(fleet.store.images.items())
        for tag in sorted(record.tests)
        if tag in record.builds
    ]


def vuln_summary(record: ImageRecord, tag: str) -> VulnerabilitySummary | None:
    scans = record.vulns.get(tag)
    return VulnerabilitySummary.model_validate(summarise(merge(scans))) if scans else None


def vulns(record: ImageRecord, tag: str) -> BuildVulnsData | None:
    """The scans of every architecture merged into one list; None when the build has not been scanned."""
    scans = record.vulns.get(tag)
    if not scans or tag not in record.builds:
        return None
    merged = merge(scans)
    newest = max(scans.values(), key=lambda s: str(s.get("db_date", "")))
    return BuildVulnsData(
        image=record.name,
        tag=tag,
        summary=VulnerabilitySummary.model_validate(summarise(merged)),
        by_arch={a: VulnerabilitySummary.model_validate(summarise(merge({a: scans[a]}))) for a in sorted(scans)},
        matches=[VulnerabilityMatch.model_validate(m) for m in merged],
        db_date=str(newest.get("db_date", "")),
        grype_version=str(newest.get("grype_version", "")),
        caveats=list(CAVEATS),
    )


def vuln_routes(fleet: Fleet) -> list[tuple[str, str]]:
    """(image, tag) for every build with a vulnerability scan."""
    return [
        (name, tag)
        for name, record in sorted(fleet.store.images.items())
        for tag in sorted(record.vulns)
        if tag in record.builds
    ]


def _diff_summary(diff: Json) -> DiffSummary:
    config = diff.get("config", {})
    env = config.get("env", {})
    changes = len(env.get("added", [])) + len(env.get("removed", [])) + len(env.get("changed", []))
    for key in ("exposed_ports", "volumes"):
        changes += len(config.get(key, {}).get("added", [])) + len(config.get(key, {}).get("removed", []))
    base = diff.get("base", {})
    return DiffSummary(
        previous_tag=diff.get("previous_tag"),
        classification=diff["classification"],
        reasons=list(diff.get("reasons", [])),
        upstream=diff["upstream"],
        base_changed=bool(base.get("changed")),
        base_from=(base.get("from") or {}).get("digest") if base.get("changed") else None,
        size=diff.get("size", {}),
        totals=diff["totals"],
        config_changes=changes,
        dockerfile_changed=sorted(arch for arch, text in diff.get("dockerfile", {}).items() if text),
    )


def build_result(build: Json) -> Literal["success", "failure", "partial"]:
    """`success`, `failure` or `partial` over every platform and the test outcome."""
    platforms = build.get("platforms", [])
    ok = sum(1 for p in platforms if p.get("result") == "success")
    tested = build["test"].get("success") if build["test"].get("enabled", True) else None
    if ok == len(platforms) and tested is not False:
        return "success"
    if ok == 0 or tested is False:
        return "failure"
    return "partial"


def report(fleet: Fleet, record: ImageRecord, tag: str) -> BuildReport | None:
    """Everything a build page shows, in one document."""
    build = record.builds.get(tag)
    if build is None:
        return None
    diff = record.diffs.get(tag)
    links = _build_links(fleet, record, build)
    ref = f"{fleet.settings.registry}/{fleet.settings.org}/{record.name}"
    return BuildReport(
        image=record.name,
        repository=build["repository"],
        tag=tag,
        branch=build["branch"],
        release_tag=build["version"].get("release_tag"),
        upstream_version=build["version"]["upstream"],
        upstream_clean=build["version"]["upstream_clean"],
        semver=build["version"].get("semver"),
        ls_build=build["version"]["ls_build"],
        created=build["created"],
        reason=build["reason"],
        commit=build["commit"],
        tags=list(build["version"].get("tags") or [tag]),
        base=build["base"],
        platforms=build["platforms"],
        index_digest=build.get("index_digest"),
        result=build_result(build),
        test_enabled=bool(build["test"].get("enabled", True)),
        test_success=build["test"]["success"] if build["test"].get("enabled", True) else None,
        tests=_test_summaries(fleet, record, build),
        classification=diff["classification"] if diff else None,
        diff=_diff_summary(diff) if diff else None,
        packages=build.get("packages"),
        notes=build.get("notes"),
        config=build["config"],
        is_newest=is_newest(record, build),
        links=ReportLinks(
            **links.model_dump(),
            run=build["workflow"]["run_url"],
            commit=f"https://github.com/{build['repository']}/commit/{build['commit']}",
            repository=f"https://github.com/{build['repository']}",
            registry=f"{ref}:{tag}",
            history=f"{fleet.site.api_root}/builds/{record.name}/",
        ),
    )


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
    if image is None or not image.manifest.get("proxy"):
        return None
    block = image.manifest["proxy"]
    return ProxyData(
        image=name,
        port=int(block["port"]),
        scheme=str(block.get("scheme", "http")),
        subdomain=proxy.subdomain(image) if block.get("subdomain", True) else None,
        subfolder=proxy.subfolder(image),
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
    if image is None or not image.manifest.get("publish", {}).get("kubernetes", {}).get("enabled", True):
        return None
    return kubernetes.render(image)


def quadlet_unit(fleet: Fleet, name: str) -> str | None:
    image = _input(fleet, name)
    if image is None or not image.manifest.get("publish", {}).get("quadlet", True):
        return None
    return quadlet.render(image)


def names_with(fleet: Fleet, kind: str) -> list[str]:
    """Image names that have a given generated document (proxy, kubernetes, quadlet)."""
    out = []
    for image in fleet.images:
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
            for tag in build["version"].get("tags", []) or [build["version"]["tag"]]:
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
