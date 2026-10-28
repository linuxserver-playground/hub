"""
Every shape the API serves. The v1 models are those of linuxserver/docker-lsio-api (root/app/models.py),
field for field and in the same order, because names and key order are part of what clients see; they
are unchanged from static-api. Everything below "Added by the hub" is new. The OpenAPI spec is generated
from these, so descriptions here are the API's documentation.
"""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

V1_CHANGELOG_ENTRIES = 3
"""How many changelog entries the v1 list endpoints include, as the original does."""
CHANGELOG_LIMIT = 100
"""How many entries /api/v1/changelog.json lists."""

IsoDate = Annotated[str, Field(description="YYYY-MM-DD", pattern=r"^\d{4}-\d{2}-\d{2}$")]
_TIMESTAMP = r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\+00:00$"
LastUpdated = Annotated[
    str,
    Field(description="When the data was last refreshed, UTC, as `YYYY-MM-DD HH:MM:SS+00:00`.", pattern=_TIMESTAMP),
]
Count = Annotated[int, Field(ge=0)]
Arch = Literal["amd64", "arm64"]

# ---------------------------------------------------------------------------------------------------
# v1, as the original API serves them


class Tag(BaseModel):
    tag: str = Field(examples=["latest"])
    desc: str


class Architecture(BaseModel):
    arch: str = Field(examples=["x86_64", "arm64"])
    tag: str = Field(description="The architecture-specific tag.", examples=["amd64-latest"])


class Changelog(BaseModel):
    date: IsoDate
    desc: str


class Volume(BaseModel):
    path: str = Field(description="Path inside the container.")
    host_path: str = Field(description="Example path on the host.")
    desc: str
    optional: bool


class Port(BaseModel):
    external: str
    internal: str = Field(description="Container port, with `/udp` when it is UDP.")
    desc: str
    optional: bool


class EnvVar(BaseModel):
    name: str
    value: str = Field(description="Example or default value.")
    desc: str
    optional: bool


class Custom(BaseModel):
    """Any other `docker run` flag, with its compose equivalent."""

    name: str = Field(description="The `docker run` flag without the leading `--`.", examples=["shm-size"])
    name_compose: str = Field(description="The compose key.", examples=["shm_size"])
    value: str | list[str]
    desc: str
    optional: bool


class SecurityOpt(BaseModel):
    run_var: str = Field(examples=["seccomp=unconfined"])
    compose_var: str = Field(examples=["seccomp:unconfined"])
    desc: str
    optional: bool


class Device(BaseModel):
    path: str
    host_path: str
    desc: str
    optional: bool


class Cap(BaseModel):
    cap_add: str = Field(examples=["NET_ADMIN"])
    desc: str
    optional: bool


class Hostname(BaseModel):
    hostname: str
    desc: str
    optional: bool


class MacAddress(BaseModel):
    mac_address: str
    desc: str
    optional: bool


class Config(BaseModel):
    """How to run the container. Each list holds required entries first, then optional ones."""

    application_setup: str | None = Field(None, description="Link to the Application Setup section of the README.")
    readonly_supported: bool | None = Field(None, description="Runs with a read-only root filesystem.")
    nonroot_supported: bool | None = Field(None, description="Runs as a non-root user.")
    privileged: bool | None = None
    networking: str | None = Field(None, description="Network mode, e.g. `host`.")
    hostname: Hostname | None = None
    mac_address: MacAddress | None = None
    env_vars: list[EnvVar] | None = None
    volumes: list[Volume] | None = None
    ports: list[Port] | None = None
    custom: list[Custom] | None = None
    security_opt: list[SecurityOpt] | None = None
    devices: list[Device] | None = None
    caps: list[Cap] | None = None


class Image(BaseModel):
    name: str = Field(examples=["sonarr"])
    initial_date: str | None = Field(None, description="Date of the image's first changelog entry.")
    github_url: str
    project_url: str | None = Field(None, description="The upstream project's website.")
    project_logo: str | None = Field(None, description="URL of the logo (`docs.logo` in the manifest).")
    description: str = Field(description="Markdown; may contain links.")
    version: str = Field(
        description="The release tag of the newest build of the `latest` branch (`<upstream>-ls<N>`), or "
        "`latest` when no build has been ingested yet."
    )
    version_timestamp: str = Field(description="UTC, as `YYYY-MM-DD HH:MM:SS+00:00`.", pattern=_TIMESTAMP)
    category: str = Field(description="Comma-separated categories from `docs.categories`.", examples=["Network,DNS"])
    stable: bool = Field(description="Whether the image publishes a `latest` tag.")
    deprecated: bool
    stars: Count = Field(description="GitHub stars of the image repository.")
    monthly_pulls: Count | None = Field(None, description="Always absent: pull statistics are not collected.")
    tags: list[Tag]
    architectures: list[Architecture]
    changelog: list[Changelog] | None = Field(
        None,
        description=f"The most recent entries; {V1_CHANGELOG_ENTRIES} in list responses, all in `ImageDetail`.",
    )
    config: Config | None = None


class Repository(BaseModel):
    linuxserver: list[Image]


class ImagesData(BaseModel):
    repositories: Repository


class ImagesResponse(BaseModel):
    status: str
    last_updated: LastUpdated
    data: ImagesData


Health = Literal["Success", "Failed"]

# ---------------------------------------------------------------------------------------------------
# Added by the hub: the catalog


class Registries(BaseModel):
    """Where the image is published."""

    ghcr: str = Field(examples=["ghcr.io/linuxserver-playground/sonarr"])
    packages_url: str = Field(description="The GitHub Packages page.")


class Snippets(BaseModel):
    """Ready-to-use commands with every parameter, optional ones marked (from `builder.snippets`)."""

    docker_compose: str
    docker_run: str


class ReleaseInfo(BaseModel):
    """The newest build of one live branch."""

    branch: str = Field(examples=["master"])
    release_tag: str = Field(description="The tag the branch publishes.", examples=["latest", "develop"])
    channel: str = Field(examples=["stable", "prerelease"])
    tag: str | None = Field(None, description="The newest release tag, `<upstream>-ls<N>`.")
    upstream_version: str | None = None
    created: str | None = Field(None, description="When the newest build ran (ISO 8601).")
    release_url: str | None = None
    test_success: bool | None = None
    base: str | None = Field(None, description="The base image reference the newest build used.")
    platforms: list[str] = Field(default_factory=list, description="Architectures that built successfully.")


class ImageLinks(BaseModel):
    builds: str
    docs: str
    documentation: str | None = Field(None, description="`docs.json`: the full documentation, section by section.")
    proxy: str | None = None
    kubernetes: str | None = None
    quadlet: str | None = None
    mods: str


class ImageDetail(Image):
    """An image with everything this API knows about it."""

    config: Config  # always present
    title: str
    kind: Literal["app", "base", "tool"] = Field(
        "app",
        description="`app` for an application; `base` for a base image, `tool` for an internal tool. Only apps are "
        "in the v1 image list, the categories, the stores and the install artefacts.",
    )
    categories: list[str] = Field(description="`category`, split and trimmed.")
    deprecation_message: str | None = Field(None, description="Why the image is deprecated, when it is.")
    setup_instructions: str | None = Field(None, description="The Application Setup section, as Markdown.")
    archived: bool = Field(description="Whether the GitHub repository is archived.")
    release_url: str | None = Field(None, description="The GitHub release for `version`.")
    upstream_version: str | None = Field(None, description="The bare upstream version of `version`.")
    base: str | None = Field(None, description="Base image family from the manifest.")
    releases: list[ReleaseInfo] = Field(description="One entry per live branch.")
    docs_url: str
    registries: Registries
    snippets: Snippets
    links: ImageLinks


class Category(BaseModel):
    name: str = Field(examples=["Media Servers"])
    slug: str = Field(examples=["media-servers"])
    count: int
    images: list[str] = Field(description="Image names, alphabetical.")


class Stats(BaseModel):
    images: int = Field(description="Current applications: base images and tools are counted apart.")
    base_images: int = Field(0, description="Current base images (`kind: base`).")
    tools: int = Field(0, description="Current internal tools (`kind: tool`).")
    deprecated: int = Field(description="Deprecated images (not counted anywhere else).")
    stars: int
    builds: int = Field(description="Build records held in data/ across all images.")
    architectures: dict[str, int] = Field(description="Images available for each architecture.")
    readonly_supported: int
    nonroot_supported: int
    updated_last_7_days: int = Field(description="Images with a build in the 7 days before `last_updated`.")
    categories: int
    first_release: str | None = Field(None, description="The oldest `initial_date`.")


class ChangelogEntry(BaseModel):
    image: str
    date: IsoDate
    desc: str


class SourceStatus(BaseModel):
    ok: bool
    checked_at: str = Field(description="When the last refresh tried this source (ISO 8601).")
    fetched_at: str | None = Field(None, description="When this source last returned data (ISO 8601).")
    error: str | None = Field(None, description="Why the last attempt failed, or what it could not fetch.")


class RejectedRelease(BaseModel):
    checked_at: str
    release_url: str | None = None
    error: str


class Status(BaseModel):
    health: Health
    images: int
    deprecated: int
    sources: dict[str, SourceStatus] = Field(
        description="`manifests` (image.yml per branch), `releases` (build bundles), `observed` (stars, GHCR tags; its "
        "`fetched_at` is `observed.json`'s), `mods` (the mods index), `proot-apps` (the PRoot Apps index)."
    )
    rejected: dict[str, RejectedRelease] = Field(
        description="Releases whose bundle failed validation, keyed `<image>@<tag>`; they are skipped until fixed."
    )


# Every new response has the same envelope as ImagesResponse.


class Envelope(BaseModel):
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    status: Literal["OK"] = "OK"
    last_updated: LastUpdated


class ImageData(BaseModel):
    image: ImageDetail


class ImageResponse(Envelope):
    data: ImageData


class CatalogData(BaseModel):
    images: list[ImageDetail]


class CatalogResponse(Envelope):
    data: CatalogData


class CategoriesData(BaseModel):
    categories: list[Category]


class CategoriesResponse(Envelope):
    data: CategoriesData


class StatsData(BaseModel):
    stats: Stats


class StatsResponse(Envelope):
    data: StatsData


class ChangelogData(BaseModel):
    changelog: list[ChangelogEntry] = Field(max_length=CHANGELOG_LIMIT)


class ChangelogResponse(Envelope):
    data: ChangelogData


class StatusData(BaseModel):
    status: Status


class StatusResponse(Envelope):
    data: StatusData


# ---------------------------------------------------------------------------------------------------
# Builds: the bundle record (schemas/bundle.schema.json in linuxserver-playground/builder)


class _Lenient(BaseModel):
    """Bundle parts keep unknown fields: a MINOR contract bump adds optional ones the hub should pass on."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)


class BuildVersion(_Lenient):
    upstream: str = Field(description="As resolved, before sanitising.")
    upstream_clean: str
    semver: str | None = None
    ls_build: int = Field(description="N in -lsN.")
    tag: str = Field(description="The primary tag, `<T-><upstream>-ls<N>`.")
    release_tag: str | None = Field(None, description="The branch's release tag (latest, develop...).")
    tags: list[str] | None = Field(None, description="Every tag pushed, unprefixed and arch-prefixed.")
    source: str | None = Field(None, description="`upstream.version.type` from the manifest.")
    source_url: str | None = None


class BuildPrevious(_Lenient):
    tag: str | None = None
    release_url: str | None = None


class BuildBase(_Lenient):
    family: str
    image: str = Field(description="FROM reference as written.")
    digest: str | None = Field(None, description="Resolved base digest at build time (amd64).")
    build_version: str | None = Field(None, description="The base image's build_version label.")


class PlatformBuild(_Lenient):
    arch: Arch
    result: Literal["success", "failure", "cancelled", "skipped"]
    digest: str | None = None
    size: int | None = Field(None, description="Sum of compressed layer sizes in bytes.")
    uncompressed_size: int | None = None
    layers: int | None = None
    runner: str | None = None
    build_seconds: float | None = None


class BuildConfig(_Lenient):
    env: list[str] | None = None
    exposed_ports: list[str] | None = None
    volumes: list[str] | None = None
    entrypoint: list[str] | None = None
    cmd: list[str] | None = None
    user: str | None = None
    working_dir: str | None = None


class InitUnit(_Lenient):
    name: str
    type: str
    depends_on: list[str]
    source: str | None = None
    script: str | None = None


class InitGraph(_Lenient):
    d2: str | None = None
    units: list[InitUnit] | None = None


class PackageSummary(_Lenient):
    count: int
    distro: str
    hash: str
    by_type: dict[str, int] | None = None


class BuildTest(_Lenient):
    enabled: bool
    success: bool
    per_arch: dict[str, bool] | None = None
    report_url: str | None = None


class BuildNotes(_Lenient):
    linuxserver: str | None = None
    upstream: str | None = None
    upstream_url: str | None = None


class BuildAsset(_Lenient):
    name: str
    size: int
    sha256: str
    url: str | None = None


class BuildWorkflow(_Lenient):
    run_id: int
    run_url: str
    workflows_ref: str
    ci_version: str | None = None


class Bundle(_Lenient):
    """`build.json` as attached to the GitHub Release, validated against the contract on ingest."""

    schema_version: int = Field(alias="schema", description="Contract major version.")
    image: str
    repository: str
    branch: str
    mode: Literal["live", "dev", "pr"]
    pull_request: int | None = None
    version: BuildVersion
    commit: str
    created: str
    reason: str
    previous: BuildPrevious | None = None
    base: BuildBase
    platforms: list[PlatformBuild]
    index_digest: str | None = None
    labels: dict[str, str]
    config: BuildConfig
    dockerfile: dict[str, str]
    init_graph: InitGraph | None = None
    packages: dict[str, PackageSummary] | None = None
    test: BuildTest
    notes: BuildNotes | None = None
    assets: list[BuildAsset]
    workflow: BuildWorkflow


class VulnerabilitySummary(BaseModel):
    """
    Counts of a build's own vulnerability scan, made when it was built (grype against each architecture's syft SBOM,
    with that day's database) and never rescanned: over distinct findings, one per vulnerability id and package across
    the architectures. The findings are the build's `vulns.json` on its repository's Pages (`links.vulns`).
    """

    critical: Count
    high: Count
    medium: Count
    low: Count
    negligible: Count
    unknown: Count
    fixed: Count = Field(description="The distribution or upstream ships a fixed version.")
    unfixed: Count = Field(description="No fix is known: `not-fixed` and `unknown` fix states.")
    wont_fix: Count = Field(description="The distribution has decided not to fix it for this release.")


class BuildLinks(BaseModel):
    build: str
    diff: str
    layers: dict[str, str] = Field(description="Per architecture.")
    packages: dict[str, str] = Field(
        description="The hub's package table per architecture; only the newest build of each branch has one. For the "
        "others, `sbom` is the build's syft document."
    )
    release: str | None = None
    pages: str = Field(
        description="The build's folder on its image repository's GitHub Pages (`https://<owner>.github.io/<repo>/"
        "builds/<tag>/`), with a trailing slash: `files.<arch>.json.gz`, `packages.<arch>.json.gz`, `vulns.json` "
        "and each architecture's unpacked test report under `<arch>/` (see `tests.json`). Served with "
        "`access-control-allow-origin: *` for the newest 5 builds of each live branch, the builds the hub holds."
    )
    files: dict[str, str] = Field(
        description="`files.<arch>.json.gz` per architecture on the repository's Pages (under `pages`): gzip served as "
        "`application/gzip`, without `Content-Encoding`."
    )
    sbom: dict[str, str] = Field(
        default_factory=dict,
        description="`packages.<arch>.json.gz`, the build's syft document, per architecture on the repository's Pages "
        "(under `pages`), served like `files`.",
    )
    run_json: str = Field(
        description="`run.json` on the Release: the control plane's record of the workflow run. A download link "
        "(Release assets send no CORS headers); 404 for releases made before control attached it."
    )
    logs_zip: str = Field(
        description="`logs.zip` on the Release: the run's masked log archive. A download link; 404 for releases made "
        "before control attached it."
    )
    test_report: str | None = Field(
        None,
        description="The build's CI results page on the website, `<site>/images/<image>/builds/<tag>/` (the hub's own "
        "`/builds/<image>/<tag>/` only redirects there).",
    )
    tests: str | None = Field(None, description="`tests.json`: the harness reports per architecture, when any exist.")
    report: str | None = Field(None, description="`report.json`: the build page aggregate.")
    vulns: str | None = Field(
        None,
        description="`vulns.json` on the repository's Pages (under `pages`), for builds that scanned themselves: the "
        "scan made when the image was built, never rescanned. `{image, tag, summary, by_arch, matches, db_date, "
        'grype_version, scanned_at, caveats}` (CONVENTIONS §6, "Repo Pages"); `summary` is `vulnerabilities`, and '
        "`caveats` say how to read the counts. The hub serves no copy.",
    )


class BuildSummary(BaseModel):
    tag: str
    branch: str
    release_tag: str | None = None
    upstream_version: str
    semver: str | None = None
    ls_build: int
    created: str
    reason: str
    commit: str
    test_success: bool | None = None
    base: BuildBase
    platforms: list[PlatformBuild]
    classification: str | None = Field(None, description="From the diff against the previous build of the branch.")
    vulnerabilities: VulnerabilitySummary | None = Field(
        None,
        description="Counts of the scan the build made of itself when it was built, for builds that have one (see "
        "`links.vulns` and its caveats). Not updated after the release.",
    )
    links: BuildLinks


class HistoryEntry(BaseModel):
    tag: str
    created: str
    release_url: str | None = None
    run_url: str | None = Field(
        None, description="The workflow run that built it; absent for releases the hub rotated out before recording it."
    )
    run_json: str | None = Field(
        None,
        description="`run.json` on the Release (a download link): the control plane's record of the run. 404 for "
        "releases made before control attached it.",
    )
    logs_zip: str | None = Field(
        None, description="`logs.zip` on the Release (a download link): the run's masked logs. 404 like `run_json`."
    )


class BuildsData(BaseModel):
    image: str
    builds: list[BuildSummary] = Field(description="Builds held in data/, newest first.")
    history: dict[str, list[HistoryEntry]] = Field(description="Every release seen per branch, newest first.")


class BuildsResponse(Envelope):
    data: BuildsData


class BuildData(BaseModel):
    build: Bundle


class BuildResponse(Envelope):
    data: BuildData


class Package(BaseModel):
    name: str
    version: str
    type: str = Field(description="syft package type: apk, deb, python, npm, binary...", examples=["apk"])
    purl: str | None = None
    licenses: list[str]


class PackagesData(BaseModel):
    image: str
    tag: str
    arch: Arch
    count: int
    packages: list[Package]


class PackagesResponse(Envelope):
    data: PackagesData


class Layer(_Lenient):
    index: int
    digest: str
    diff_id: str | None = None
    size: int = Field(description="Compressed bytes.")
    uncompressed_size: int | None = None
    created_by: str | None = Field(None, description="The instruction as BuildKit recorded it.")
    dockerfile_lines: list[int] | None = Field(None, description="`[start, end]` lines in the Dockerfile (1-based).")
    from_base: bool | None = Field(None, description="The layer comes from the base image.")
    empty: bool | None = None


FromBaseSource = Literal["registry", "count", "harness"]


class LayersData(BaseModel):
    image: str
    tag: str
    arch: Arch
    base_layers: int | None = Field(None, description="How many leading layers belong to the base image, when known.")
    from_base_source: FromBaseSource | None = Field(
        None,
        description="How `from_base` was decided: `registry` (the base's layer digests from GHCR), `count` (the "
        "base's layer count, digests known for another architecture only), `harness` (the ci harness's own flags). "
        "Absent when the hub has nothing to go on.",
    )
    layers: list[Layer] = Field(
        description="`from_base` marks the base image's layers; `dockerfile_lines` is the `[start, end]` line range "
        "of the instruction that made each of the others, where `created_by` matches the Dockerfile in `build.json`."
    )


class LayersResponse(Envelope):
    data: LayersData


# ---------------------------------------------------------------------------------------------------
# Test reports (schemas/test-report.schema.json in linuxserver-playground/builder)


class TestCase(_Lenient):
    name: str
    status: str = Field(examples=["PASS", "FAIL", "SKIP"])
    message: str | None = None
    seconds: float | None = None


class TestRuntime(_Lenient):
    rss_bytes: int | None = None
    pids: int | None = None
    listening_tcp: list[int] | None = None
    listening_udp: list[int] | None = None
    s6_services: list[str] | None = None
    changed_paths: int | None = None


class TestReport(_Lenient):
    """`test.<arch>.json` as the ci harness attached it to the Release, validated against the contract on ingest."""

    schema_version: int = Field(alias="schema")
    image: str
    tag: str
    arch: Arch
    started: str | None = None
    finished: str | None = None
    success: bool
    runner: str | None = None
    ci_version: str | None = None
    engine: str | None = None
    startup_seconds: float | None = None
    tests: list[TestCase] = Field(default_factory=list)
    warnings: dict[str, str] | None = None
    files: dict[str, str] | None = Field(None, description="Files in `test.<arch>.tar.gz`, by kind.")
    runtime: TestRuntime | None = None


class TestArchSummary(BaseModel):
    success: bool
    passed: int
    failed: int
    total: int
    failed_tests: list[str] = Field(description="Names of the tests that did not pass.")
    startup_seconds: float | None = None
    listening_ports: list[str] = Field(description="`<port>/tcp` and `<port>/udp` the container listened on.")
    warnings: int = Field(description="How many checks warned.")
    rss_bytes: int | None = None
    pids: int | None = None
    tarball: str | None = Field(None, description="`test.<arch>.tar.gz` on the Release (a download link).")
    files: dict[str, str] = Field(
        default_factory=dict,
        description="The report's files unpacked on the repository's Pages, by the kind `files` names in the report "
        "(`screenshot`, `container_log`, `browser_log`, `sysinfo`, `shellcheck`). `package_diff.txt` sits next to them "
        "when the harness wrote one.",
    )


class BuildTestsData(BaseModel):
    image: str
    tag: str
    enabled: bool = Field(description="`test.enabled` of the build.")
    success: bool | None = Field(None, description="`test.success` of the build; None when tests were disabled.")
    report_url: str = Field(description="The build's CI results page on the website (`links.test_report`).")
    summary: dict[str, TestArchSummary] = Field(description="Per architecture.")
    reports: dict[str, TestReport] = Field(description="The harness reports per architecture, as received.")


class BuildTestsResponse(Envelope):
    data: BuildTestsData


# ---------------------------------------------------------------------------------------------------
# Diffs

Classification = Literal["upstream", "packages", "linuxserver", "base", "mixed", "none", "initial"]


class PackageChange(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str
    version: str | None = Field(None, description="For added and removed packages.")
    from_version: str | None = Field(None, alias="from", description="For upgrades and downgrades.")
    to: str | None = None
    purl: str | None = None


class EcosystemDiff(BaseModel):
    added: list[PackageChange]
    removed: list[PackageChange]
    upgraded: list[PackageChange]
    downgraded: list[PackageChange]


class ListDiff(BaseModel):
    added: list[str]
    removed: list[str]


class EnvChange(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str
    from_value: str | None = Field(None, alias="from")
    to: str | None = None


class EnvDiff(BaseModel):
    added: list[str]
    removed: list[str]
    changed: list[EnvChange]


class ConfigDiff(BaseModel):
    env: EnvDiff
    exposed_ports: ListDiff
    volumes: ListDiff


class ValueChange(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_value: str | None = Field(None, alias="from")
    to: str | None = None
    changed: bool


class BaseChange(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_base: BuildBase | None = Field(None, alias="from")
    to: BuildBase
    changed: bool


class SizeChange(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_size: int | None = Field(None, alias="from")
    to: int | None = None
    delta: int | None = None


class PackageTotals(BaseModel):
    added: int
    removed: int
    upgraded: int
    downgraded: int


class Diff(BaseModel):
    """What changed between a build and the previous build of the same branch."""

    image: str
    branch: str
    tag: str
    previous_tag: str | None = Field(None, description="None for the first build of a branch the hub has seen.")
    classification: Classification = Field(
        description="`upstream`: the upstream version changed. `packages`: only packages changed. `linuxserver`: "
        "the Dockerfile (or a push with no other change) changed with the same upstream. `base`: the base image "
        "digest changed. `mixed`: more than one of those. `none`: an identical rebuild. `initial`: no previous build."
    )
    reasons: list[str] = Field(description="The signals behind `classification`, for humans.")
    upstream: ValueChange
    base: BaseChange
    size: dict[str, SizeChange] = Field(description="Compressed size per architecture.")
    config: ConfigDiff
    dockerfile: dict[str, str] = Field(description="Unified diff per architecture; empty when unchanged.")
    packages: dict[str, dict[str, EcosystemDiff]] | None = Field(
        None, description="Per architecture, per ecosystem. None when the previous package table was not available."
    )
    totals: PackageTotals


class DiffData(BaseModel):
    diff: Diff


class DiffResponse(Envelope):
    data: DiffData


# ---------------------------------------------------------------------------------------------------
# The build page aggregate


class DiffSummary(BaseModel):
    """`diff.json` without the package lists: enough for a build page's change strip."""

    previous_tag: str | None = None
    classification: Classification
    reasons: list[str]
    upstream: ValueChange
    base_changed: bool
    base_from: str | None = Field(None, description="The previous build's base digest, when it changed.")
    size: dict[str, SizeChange]
    totals: PackageTotals
    config_changes: int = Field(description="Env, port and volume entries added, removed or changed.")
    dockerfile_changed: list[str] = Field(description="Architectures whose Dockerfile differs from the previous build.")


class ReportLinks(BuildLinks):
    run: str = Field(description="The workflow run.")
    commit: str
    repository: str
    registry: str = Field(description="The image reference with this build's tag.")
    history: str = Field(description="The image's build list on the website, `<site>/images/<image>/#builds`.")


class BuildReport(BaseModel):
    """What a build page shows: the record's facts, platforms, test and diff summaries and every link."""

    image: str
    repository: str
    tag: str
    branch: str
    release_tag: str | None = None
    upstream_version: str
    upstream_clean: str
    semver: str | None = None
    ls_build: int
    created: str
    reason: str
    commit: str
    tags: list[str] = Field(description="Every tag pushed, unprefixed and arch-prefixed.")
    base: BuildBase
    platforms: list[PlatformBuild]
    index_digest: str | None = None
    result: Literal["success", "failure", "partial"] = Field(
        description="`success` when every platform built and tests passed (or were disabled); `failure` when none "
        "built or tests failed; `partial` otherwise."
    )
    test_enabled: bool
    test_success: bool | None = None
    tests: dict[str, TestArchSummary] = Field(description="Per architecture, when the harness report exists.")
    classification: Classification | None = None
    diff: DiffSummary | None = None
    packages: dict[str, PackageSummary] | None = Field(None, description="Package counts per architecture.")
    notes: BuildNotes | None = None
    config: BuildConfig
    is_newest: bool = Field(description="Whether this is the newest build of its branch the hub holds.")
    links: ReportLinks


class BuildReportData(BaseModel):
    report: BuildReport


class BuildReportResponse(Envelope):
    data: BuildReportData


# ---------------------------------------------------------------------------------------------------
# Mods


class ModEnv(BaseModel):
    name: str
    description: str
    default: str | None = None
    required: bool = False


class ModUpstream(BaseModel):
    url: str | None = Field(None, description="The project's website (`mod.yml` `upstream.url`).")
    type: str = Field(description="`upstream.version.type`, e.g. `github_release` or `combined`.")
    source: str = Field(description="The version source in short.", examples=["github_release cloudflare/cloudflared"])


class ModBuild(BaseModel):
    line: str | None = Field(
        None,
        description="The version line (`mod.yml` `upstream.lines` name); null for the default line, the one the "
        "floating `:<branch>` tag follows.",
    )
    version: str | None = Field(
        None, description="The upstream version built (the image's version label); null for a mod without one."
    )
    built_at: str | None = Field(None, description="When the newest build of the line was made (the image config).")
    pin: str | None = Field(
        None,
        description="The exact tag of that build, to pin it: `<branch>-<version>`, or `<branch>-<sha7>` for a mod "
        "without a version.",
        examples=["ghcr.io/linuxserver-playground/mods:code-server-golang-1.27.3"],
    )
    tags: list[str] = Field(
        default_factory=list,
        description="The floating tags that follow the line: `:<branch>` for the default line, then the line's "
        "major and minor tags.",
    )
    digest: str | None = Field(None, description="The image's digest.")
    revision: str | None = Field(None, description="The docker-mods commit it was built from.")


class Mod(BaseModel):
    name: str = Field(examples=["python3"])
    target: str = Field(description="The image the mod applies to, or `universal`.")
    title: str
    summary: str
    branch: str = Field(description="The docker-mods branch.")
    url: str
    image: str = Field(
        description="The `DOCKER_MODS` value.", examples=["ghcr.io/linuxserver-playground/mods:universal-git"]
    )
    maintainers: list[str]
    platforms: list[str]
    bases: list[str]
    env: list[ModEnv]
    deprecated: bool
    deprecation_message: str | None = None
    applies_to: list[str] = Field(
        description="The images the mod is for: its target, then the images its `mod.yml` lists under `images`."
    )
    docs: str | None = None
    upstream: ModUpstream | None = Field(
        None,
        description="Where the tool version the mod pins comes from. The control plane checks it hourly and builds "
        "the mod when a new version has no `<branch>-<version>` tag yet.",
    )
    builds: list[ModBuild] = Field(
        default_factory=list,
        description="What `ghcr.io/linuxserver-playground/mods` holds for the mod, one entry per version line, the "
        "default line first; empty until it is published. Read hourly from the registry.",
    )
    source: Literal["playground"] = Field(
        description="A `mod.yml` branch of linuxserver-playground/docker-mods, published at "
        "`ghcr.io/linuxserver-playground/mods`."
    )


class ModsData(BaseModel):
    source: str = Field(
        description="Where the index came from: `mod.yml` on each branch of linuxserver-playground/docker-mods."
    )
    mods: list[Mod]


class ModsResponse(Envelope):
    data: ModsData


class ImageModsData(BaseModel):
    image: str
    mods: list[Mod] = Field(description="Mods targeting this image, then universal mods.")


class ImageModsResponse(Envelope):
    data: ImageModsData


# ---------------------------------------------------------------------------------------------------
# PRoot Apps


class ProotApp(BaseModel):
    name: str = Field(description="What `proot-apps install` takes.", examples=["firefox"])
    title: str = Field(description="`full_name` in metadata.yml.", examples=["Firefox"])
    category: str = Field(examples=["Network"])
    description: str
    platforms: list[str] = Field(examples=[["amd64", "arm64"]])
    icon: str | None = Field(None, description="The app's icon in the proot-apps repository.")
    image: str = Field(examples=["ghcr.io/linuxserver-playground/proot-apps:firefox"])
    url: str = Field(description="The app's folder in the proot-apps repository.")


class ProotCli(BaseModel):
    version: str = Field(description="The newest release of the `proot-apps` CLI.", examples=["0.5.5"])
    url: str
    published_at: str | None = None


class ProotAppsData(BaseModel):
    source: str = Field(
        description="Where the index came from: `metadata/metadata.yml` of linuxserver-playground/proot-apps."
    )
    cli: ProotCli | None = Field(
        None, description="The CLI release the install command downloads; null until one exists."
    )
    apps: list[ProotApp] = Field(description="Every app that is not disabled, by title.")


class ProotAppsResponse(Envelope):
    data: ProotAppsData


# ---------------------------------------------------------------------------------------------------
# Proxy, packages index, fleet, stores


class ProxyData(BaseModel):
    image: str
    port: int
    scheme: str
    subdomain: str | None = Field(None, description="The `<name>.subdomain.conf.sample` text.")
    subfolder: str | None = Field(None, description="The `<name>.subfolder.conf.sample` text, when supported.")
    caddy: str | None = Field(
        None, description="A reference Caddyfile site block with the same upstream and open API paths."
    )
    traefik: str | None = Field(None, description="Reference Traefik labels for the image's compose service.")
    base_url_note: str | None = None
    config: dict[str, Any] = Field(description="The manifest's `proxy` block.")


class ProxyResponse(Envelope):
    data: ProxyData


class DocSection(BaseModel):
    id: str = Field(description="Slug of the title, stable across images: `application-setup`, `support-info`.")
    title: str = Field(description="The `##` heading as written.")
    markdown: str = Field(description="The section body in GitHub-flavoured Markdown, without its heading.")


class DocsData(BaseModel):
    """The image's full documentation, split at its `##` headings: the README builder renders from `image.yml`."""

    image: str
    sections: list[DocSection]


class DocsResponse(Envelope):
    data: DocsData


class PackageHolder(BaseModel):
    image: str
    tag: str
    branch: str
    arch: Arch
    version: str
    type: str
    purl: str | None = None


class PackageData(BaseModel):
    name: str
    slug: str
    types: list[str]
    versions: list[str] = Field(description="Distinct versions shipped, newest-first by sort order.")
    images: list[str]
    holders: list[PackageHolder]


class PackageResponse(Envelope):
    data: PackageData


class PackageIndexEntry(BaseModel):
    name: str
    slug: str
    types: list[str]
    images: int


class PackageIndexData(BaseModel):
    packages: list[PackageIndexEntry]


class PackageIndexResponse(Envelope):
    data: PackageIndexData


class BaseDigest(BaseModel):
    digest: str
    first_seen: str
    last_seen: str
    images: list[str]


class BaseUsage(BaseModel):
    image: str = Field(description="The FROM reference.", examples=["ghcr.io/linuxserver/baseimage-alpine:3.24"])
    family: str
    images: list[str] = Field(description="Images whose newest build uses this base.")
    newest_digest: str | None = Field(None, description="The most recently built-against digest.")
    newest_seen: str | None = Field(None, description="When a build first used `newest_digest`.")
    digests: list[BaseDigest]


class BasesData(BaseModel):
    bases: list[BaseUsage]


class BasesResponse(Envelope):
    data: BasesData


class StaleImage(BaseModel):
    image: str
    branch: str
    tag: str
    built: str
    base: str
    base_digest: str | None = None
    newest_base_digest: str | None = None
    newest_base_built: str = Field(description="When the newer base was first seen in a build (or released).")
    reason: str


class StalenessData(BaseModel):
    stale: list[StaleImage]
    checked: int = Field(description="Builds considered.")


class StalenessResponse(Envelope):
    data: StalenessData


class StoreEntry(BaseModel):
    platform: str
    name: str
    url: str
    how_to: str


class StoresData(BaseModel):
    stores: list[StoreEntry]


class StoresResponse(Envelope):
    data: StoresData
