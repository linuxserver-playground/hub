"""
The API as a FastAPI app, as static-api had it: every endpoint is a route with a Pydantic response model and
the OpenAPI spec is generated from them. The static build requests every route and writes the responses to
files; the same app runs as a live server for development (python -m lsio_hub.serve).
"""

import json
from functools import partial
from typing import Annotated, Any

import yaml
from fastapi import FastAPI, HTTPException, Path, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import responses
from .config import PUBLIC_DIR, WEBSITE, SiteConfig
from .feed import changelog_feed
from .fleet import Fleet
from .models import (
    BasesResponse,
    BuildData,
    BuildReportData,
    BuildReportResponse,
    BuildResponse,
    BuildsResponse,
    BuildTestsResponse,
    BuildVulnsResponse,
    CatalogData,
    CatalogResponse,
    CategoriesData,
    CategoriesResponse,
    ChangelogData,
    ChangelogResponse,
    DiffData,
    DiffResponse,
    DocsResponse,
    Health,
    ImageData,
    ImageDetail,
    ImageModsResponse,
    ImageResponse,
    ImagesResponse,
    LayersResponse,
    ModsResponse,
    PackageIndexData,
    PackageIndexResponse,
    PackageResponse,
    PackagesResponse,
    ProotAppsResponse,
    ProxyResponse,
    StalenessResponse,
    StatsData,
    StatsResponse,
    StatusData,
    StatusResponse,
    StoresData,
    StoresResponse,
)
from .site import render_index, render_not_found
from .store import ImageRecord

DESCRIPTION = """
Versions, tags, architectures, changelogs and container parameters for every LinuxServer.io image, every
build with its packages, layers and changes, the mods index, the PRoot Apps index, and compose, Kubernetes,
quadlet and reverse proxy snippets.

Every endpoint is a plain `GET` with no authentication. Fields that have no value are omitted rather than
`null`. Query parameters are not supported: `include_config` and `include_deprecated` are separate files
under Compatibility.
"""

TAGS = [
    {"name": "Images", "description": "Every image, or one image in full."},
    {
        "name": "Builds",
        "description": "Every build of an image: the build record, packages, layers and the diff.",
    },
    {"name": "Mods", "description": "Docker mods, fleet-wide and per image."},
    {"name": "PRoot Apps", "description": "Desktop apps installed without privileges by the proot-apps CLI."},
    {"name": "Packages", "description": "Which images ship a package, and in which versions."},
    {"name": "Fleet", "description": "Numbers, categories, base images and changes across all images."},
    {"name": "Service", "description": "Whether the data is fresh, and where the store output is."},
    {
        "name": "Compatibility",
        "description": "The api.linuxserver.io endpoints, with the same paths and response shapes. Prefer the "
        "`.json` paths: they are identical and served as `application/json`.",
    },
]


class YamlResponse(PlainTextResponse):
    media_type = "application/yaml"


class AtomResponse(PlainTextResponse):
    media_type = "application/atom+xml"


class UnitResponse(PlainTextResponse):
    media_type = "text/plain"


ImageName = Annotated[
    str, Path(description="The image name, as in `ghcr.io/linuxserver-playground/<name>`.", examples=["sonarr"])
]
BuildTag = Annotated[str, Path(description="A release tag, `<upstream>-ls<N>`.", examples=["4.0.20.3014-ls1"])]
ArchName = Annotated[str, Path(description="`amd64` or `arm64`.", examples=["amd64"])]
PackageSlug = Annotated[
    str, Path(description="A package name as listed in `/api/v1/packages.json` (`slug`).", examples=["curl"])
]

NOT_FOUND: dict[int | str, dict[str, Any]] = {404: {"description": "There is no such image, build or document."}}


def create_app(fleet: Fleet, config: SiteConfig) -> FastAPI:
    app = FastAPI(
        title="LinuxServer Hub API",
        version="2.0",
        summary="Metadata, builds and generated artefacts for every LinuxServer.io container image.",
        description=DESCRIPTION,
        servers=[{"url": config.api_root}],
        openapi_tags=TAGS,
        contact={"name": "LinuxServer.io", "url": f"{WEBSITE}support/"},
        license_info={"name": "GPL-3.0", "url": "https://www.gnu.org/licenses/gpl-3.0.html"},
        openapi_url=None,
        docs_url=None,
        redoc_url=None,
    )
    get = partial(app.get, response_model_exclude_none=True)
    images = {image.name: image for image in fleet.images}

    def find(name: str) -> ImageDetail:
        if name not in images:
            raise HTTPException(status_code=404)
        return images[name]

    def record(name: str) -> ImageRecord:
        found = fleet.record(name)
        if found is None or name not in images:
            raise HTTPException(status_code=404)
        return found

    def envelope[T](model: type[T], **data: Any) -> T:
        return model(last_updated=fleet.last_updated, **data)  # type: ignore[call-arg]

    def or_404[T](value: T | None) -> T:
        if value is None:
            raise HTTPException(status_code=404)
        return value

    # ------------------------------------------------------------------------------------- Images

    @get(
        "/api/v1/catalog/{name}.json",
        tags=["Images"],
        operation_id="getImage",
        summary="Get one image",
        responses=NOT_FOUND,
    )
    def get_image(name: ImageName) -> ImageResponse:
        """
        Everything about one image, deprecated images included: the full changelog, container configuration,
        setup instructions, the newest build of every live branch and generated `docker run` and compose snippets.
        """
        return envelope(ImageResponse, data=ImageData(image=find(name)))

    @get(
        "/api/v1/catalog/{name}/docker-compose.yml",
        tags=["Images"],
        operation_id="getImageCompose",
        summary="Get a compose file for one image",
        response_class=YamlResponse,
        responses=NOT_FOUND,
    )
    def get_image_compose(name: ImageName) -> str:
        """A Docker Compose file with the image's recommended settings, optional ones marked `#optional`."""
        return find(name).snippets.docker_compose

    @get(
        "/api/v1/catalog/{name}/proxy.json",
        tags=["Images"],
        operation_id="getImageProxy",
        summary="Get the SWAG proxy confs",
        responses=NOT_FOUND,
    )
    def get_image_proxy(name: ImageName) -> ProxyResponse:
        """The `<name>.subdomain.conf.sample` and `.subfolder.conf.sample` texts from the manifest's `proxy` block."""
        find(name)
        return envelope(ProxyResponse, data=or_404(responses.proxy_data(fleet, name)))

    @get(
        "/api/v1/catalog/{name}/docs.json",
        tags=["Images"],
        operation_id="getImageDocs",
        summary="Get the full documentation",
        responses=NOT_FOUND,
    )
    def get_image_docs(name: ImageName) -> DocsResponse:
        """The README builder renders from the manifest, split at its `##` headings: setup, usage, parameters,
        environment variables from files, user and group identifiers, support, updating, building locally."""
        find(name)
        return envelope(DocsResponse, data=or_404(responses.docs_data(fleet, name)))

    @get(
        "/api/v1/catalog/{name}/kubernetes.yaml",
        tags=["Images"],
        operation_id="getImageKubernetes",
        summary="Get a Kubernetes manifest",
        response_class=YamlResponse,
        responses=NOT_FOUND,
    )
    def get_image_kubernetes(name: ImageName) -> str:
        """ConfigMap, PersistentVolumeClaims, a Deployment or StatefulSet and a Service; security notes as comments."""
        find(name)
        return or_404(responses.kubernetes_yaml(fleet, name))

    @get(
        "/api/v1/catalog/{name}/quadlet.container",
        tags=["Images"],
        operation_id="getImageQuadlet",
        summary="Get a Podman quadlet unit",
        response_class=UnitResponse,
        responses=NOT_FOUND,
    )
    def get_image_quadlet(name: ImageName) -> str:
        """A `.container` unit for Podman's systemd integration, optional parameters commented out."""
        find(name)
        return or_404(responses.quadlet_unit(fleet, name))

    @get(
        "/api/v1/catalog/{name}/mods.json",
        tags=["Mods"],
        operation_id="getImageMods",
        summary="Get the mods for one image",
        responses=NOT_FOUND,
    )
    def get_image_mods(name: ImageName) -> ImageModsResponse:
        """Mods targeting this image, then the universal ones."""
        find(name)
        return envelope(ImageModsResponse, data=responses.image_mods(fleet, name))

    @get("/api/v1/catalog.json", tags=["Images"], operation_id="getCatalog", summary="Get every image in full")
    def get_catalog() -> CatalogResponse:
        """Every image, deprecated ones included, with the same detail as `/api/v1/catalog/{name}.json`."""
        return envelope(CatalogResponse, data=CatalogData(images=fleet.images))

    # ------------------------------------------------------------------------------------- Builds

    @get(
        "/api/v1/catalog/{name}/builds.json",
        tags=["Builds"],
        operation_id="getBuilds",
        summary="List the builds of an image",
        responses=NOT_FOUND,
    )
    def get_builds(name: ImageName) -> BuildsResponse:
        """Every build held by the hub (the newest ten per branch), newest first, and the release history per branch."""
        return envelope(BuildsResponse, data=responses.builds(fleet, record(name)))

    @get(
        "/api/v1/catalog/{name}/builds/{tag}.json",
        tags=["Builds"],
        operation_id="getBuild",
        summary="Get one build record",
        responses=NOT_FOUND,
    )
    def get_build(name: ImageName, tag: BuildTag) -> BuildResponse:
        """The `build.json` attached to the GitHub Release, as received (validated against the bundle contract)."""
        return envelope(BuildResponse, data=BuildData(build=or_404(responses.bundle(record(name), tag))))

    @get(
        "/api/v1/catalog/{name}/builds/{tag}/diff.json",
        tags=["Builds"],
        operation_id="getBuildDiff",
        summary="Get what changed in a build",
        responses=NOT_FOUND,
    )
    def get_build_diff(name: ImageName, tag: BuildTag) -> DiffResponse:
        """Packages, config, base, size and Dockerfile changes against the previous build of the same branch."""
        return envelope(DiffResponse, data=DiffData(diff=or_404(responses.diff(record(name), tag))))

    @get(
        "/api/v1/catalog/{name}/builds/{tag}/packages.{arch}.json",
        tags=["Builds"],
        operation_id="getBuildPackages",
        summary="Get the packages of a build",
        responses=NOT_FOUND,
    )
    def get_build_packages(name: ImageName, tag: BuildTag, arch: ArchName) -> PackagesResponse:
        """
        The normalised package table (name, version, type, purl, licenses) from the syft SBOM. Held for the newest
        build of each branch; older builds keep their `packages.<arch>.json.gz` on the Release.
        """
        return envelope(PackagesResponse, data=or_404(responses.packages_table(record(name), tag, arch)))

    @get(
        "/api/v1/catalog/{name}/builds/{tag}/layers.{arch}.json",
        tags=["Builds"],
        operation_id="getBuildLayers",
        summary="Get the layers of a build",
        responses=NOT_FOUND,
    )
    def get_build_layers(name: ImageName, tag: BuildTag, arch: ArchName) -> LayersResponse:
        """
        `layers.<arch>.json` from the Release: every layer with its digest, size and Dockerfile instruction, plus
        `from_base` (from the base image's manifest on GHCR) and `dockerfile_lines` (matched against the Dockerfile).
        """
        return envelope(LayersResponse, data=or_404(responses.layers(record(name), tag, arch, fleet.store.bases)))

    @get(
        "/api/v1/catalog/{name}/builds/{tag}/tests.json",
        tags=["Builds"],
        operation_id="getBuildTests",
        summary="Get the test reports of a build",
        responses=NOT_FOUND,
    )
    def get_build_tests(name: ImageName, tag: BuildTag) -> BuildTestsResponse:
        """
        The ci harness's `test.<arch>.json` per architecture as received, with a summary per architecture (result,
        startup time, listening ports, failed tests) and the report page URL. Only for builds that have a report.
        """
        return envelope(BuildTestsResponse, data=or_404(responses.tests(fleet, record(name), tag)))

    @get(
        "/api/v1/catalog/{name}/builds/{tag}/report.json",
        tags=["Builds"],
        operation_id="getBuildReport",
        summary="Get the build page aggregate",
        responses=NOT_FOUND,
    )
    def get_build_report(name: ImageName, tag: BuildTag) -> BuildReportResponse:
        """
        Everything a build page shows in one document: the record's facts, platforms, the test summary per
        architecture, the diff summary (without the package lists) and every link.
        """
        return envelope(
            BuildReportResponse, data=BuildReportData(report=or_404(responses.report(fleet, record(name), tag)))
        )

    @get(
        "/api/v1/catalog/{name}/builds/{tag}/vulns.json",
        tags=["Builds"],
        operation_id="getBuildVulnerabilities",
        summary="Get the vulnerability scan of a build",
        responses=NOT_FOUND,
    )
    def get_build_vulns(name: ImageName, tag: BuildTag) -> BuildVulnsResponse:
        """
        grype's findings against the build's syft SBOM, per architecture and merged (one row per vulnerability and
        package), with counts per severity and fix state. The data is dated by the vulnerability database, not the
        build: the newest build of each branch is rescanned when the database moves. Read `caveats` before showing
        the numbers. Only for builds that have been scanned.
        """
        return envelope(BuildVulnsResponse, data=or_404(responses.vulns(record(name), tag)))

    # ------------------------------------------------------------------------------------- Mods, packages

    @get("/api/v1/mods.json", tags=["Mods"], operation_id="getMods", summary="Get every mod")
    def get_mods() -> ModsResponse:
        """The mods index from the mod.yml on every branch of docker-mods."""
        return envelope(ModsResponse, data=responses.mods(fleet))

    @get(
        "/api/v1/proot-apps.json",
        tags=["PRoot Apps"],
        operation_id="getProotApps",
        summary="Get every PRoot app",
    )
    def get_proot_apps() -> ProotAppsResponse:
        """The desktop apps `proot-apps` installs, from metadata.yml in the proot-apps repository, without the
        disabled ones, and the CLI release the install command downloads."""
        return envelope(ProotAppsResponse, data=responses.proot_apps(fleet))

    @get("/api/v1/packages.json", tags=["Packages"], operation_id="getPackages", summary="List every package")
    def get_packages() -> PackageIndexResponse:
        """Every package name the newest builds ship, with the slug of its `/api/v1/packages/{package}.json` file."""
        return envelope(PackageIndexResponse, data=PackageIndexData(packages=responses.package_index(fleet)))

    @get(
        "/api/v1/packages/{package}.json",
        tags=["Packages"],
        operation_id="getPackage",
        summary="Get who ships a package",
        responses=NOT_FOUND,
    )
    def get_package(package: PackageSlug) -> PackageResponse:
        """Which images ship the package, in which versions, per branch and architecture."""
        return envelope(PackageResponse, data=or_404(responses.package_detail(fleet, package)))

    # ------------------------------------------------------------------------------------- Fleet

    @get("/api/v1/categories.json", tags=["Fleet"], operation_id="getCategories", summary="Get image categories")
    def get_categories() -> CategoriesResponse:
        """Categories of the current (not deprecated) images, most populated first."""
        return envelope(CategoriesResponse, data=CategoriesData(categories=responses.categories(fleet)))

    @get("/api/v1/stats.json", tags=["Fleet"], operation_id="getStats", summary="Get fleet statistics")
    def get_stats() -> StatsResponse:
        """Headline numbers across the current (not deprecated) images."""
        return envelope(StatsResponse, data=StatsData(stats=responses.stats(fleet)))

    @get("/api/v1/changelog.json", tags=["Fleet"], operation_id="getChangelog", summary="Get recent changelog entries")
    def get_changelog() -> ChangelogResponse:
        """The 100 most recent changelog entries across the current images, newest first."""
        return envelope(ChangelogResponse, data=ChangelogData(changelog=responses.recent_changelog(fleet)))

    @get(
        "/api/v1/changelog.xml",
        tags=["Fleet"],
        operation_id="getChangelogFeed",
        summary="Subscribe to changelog entries",
        response_class=AtomResponse,
    )
    def get_changelog_feed() -> str:
        """The same entries as `/api/v1/changelog.json`, as an Atom feed."""
        return changelog_feed(fleet, config)

    @get("/api/v1/fleet/bases.json", tags=["Fleet"], operation_id="getBases", summary="Get base image usage")
    def get_bases() -> BasesResponse:
        """Every base image reference the fleet builds from, which images use it, and the digests seen over time."""
        return envelope(BasesResponse, data=responses.bases(fleet))

    @get(
        "/api/v1/fleet/staleness.json",
        tags=["Fleet"],
        operation_id="getStaleness",
        summary="Get images built on an old base",
    )
    def get_staleness() -> StalenessResponse:
        """Images whose newest build predates a newer build of their base (a newer digest seen in another build)."""
        return envelope(StalenessResponse, data=responses.staleness(fleet))

    # ------------------------------------------------------------------------------------- Service

    @get("/api/v1/status.json", tags=["Service"], operation_id="getStatus", summary="Get data freshness")
    def get_status() -> StatusResponse:
        """The outcome of the last refresh of each data source and the releases whose bundle was rejected."""
        return envelope(StatusResponse, data=StatusData(status=responses.status(fleet)))

    @get("/api/v1/stores/index.json", tags=["Service"], operation_id="getStores", summary="Get every store URL")
    def get_stores() -> StoresResponse:
        """Where each generated store lives and how to import it."""
        return envelope(StoresResponse, data=StoresData(stores=responses.stores_index(fleet)))

    # ------------------------------------------------------------------------------------- Compatibility

    @get(
        "/health.json",
        tags=["Compatibility"],
        operation_id="getHealthJson",
        summary="Get the health status (JSON)",
        description="The same as `/health`, served as `application/json`.",
    )
    @get("/health", tags=["Compatibility"], operation_id="health_health_get", summary="Get the health status")
    def health() -> Health:
        """`"Success"` when the last manifest refresh worked, `"Failed"` when it did not (old data still served)."""
        return fleet.health

    @get(
        "/api/v1/images.json",
        tags=["Compatibility"],
        operation_id="listImages",
        summary="List current images",
        description="Current images without their configuration. The same as `/api/v1/images`.",
    )
    @get(
        "/api/v1/images",
        tags=["Compatibility"],
        operation_id="images_api_v1_images_get",
        summary="Get a list of images",
    )
    def images_list() -> ImagesResponse:
        """
        Current images without their configuration: the original endpoint with its default parameters.

        | Original | File |
        | --- | --- |
        | `/api/v1/images` | `/api/v1/images.json` |
        | `?include_config=true` | `/api/v1/images.config.json` |
        | `?include_deprecated=true` | `/api/v1/images.deprecated.json` |
        | `?include_config=true&include_deprecated=true` | `/api/v1/images.config.deprecated.json` |
        """
        return responses.images_response(fleet)

    @get(
        "/api/v1/images.config.json",
        tags=["Compatibility"],
        operation_id="listImagesWithConfig",
        summary="List current images with configuration",
    )
    def images_config() -> ImagesResponse:
        """The original `/api/v1/images?include_config=true`."""
        return responses.images_response(fleet, include_config=True)

    @get(
        "/api/v1/images.deprecated.json",
        tags=["Compatibility"],
        operation_id="listImagesWithDeprecated",
        summary="List all images, deprecated included",
    )
    def images_deprecated() -> ImagesResponse:
        """The original `/api/v1/images?include_deprecated=true`."""
        return responses.images_response(fleet, include_deprecated=True)

    @get(
        "/api/v1/images.config.deprecated.json",
        tags=["Compatibility"],
        operation_id="listImagesWithConfigAndDeprecated",
        summary="List all images with configuration",
    )
    def images_config_deprecated() -> ImagesResponse:
        """The original `/api/v1/images?include_config=true&include_deprecated=true`."""
        return responses.images_response(fleet, include_config=True, include_deprecated=True)

    # ------------------------------------------------------------------------------------- Spec and docs

    def spec() -> dict[str, Any]:
        """The generated spec without the 422 responses FastAPI adds to routes with path parameters."""
        if app.openapi_schema is None:
            generated = app.openapi()
            for item in generated["paths"].values():
                for operation in item.values():
                    operation["responses"].pop("422", None)
            schemas = generated.get("components", {}).get("schemas", {})
            for name in ("HTTPValidationError", "ValidationError"):
                schemas.pop(name, None)
        return app.openapi()

    @app.get("/openapi.json", include_in_schema=False)
    def openapi_json() -> Response:
        return Response(json.dumps(spec(), indent=2, ensure_ascii=False) + "\n", media_type="application/json")

    @app.get("/openapi.yaml", include_in_schema=False, response_class=YamlResponse)
    def openapi_yaml() -> str:
        return yaml.dump(
            spec(),
            Dumper=getattr(yaml, "CSafeDumper", yaml.SafeDumper),
            sort_keys=False,
            allow_unicode=True,
            width=1000,
        )

    @app.get("/", include_in_schema=False, response_class=HTMLResponse)
    def docs() -> str:
        return render_index(fleet, spec(), config)

    @app.exception_handler(StarletteHTTPException)
    def not_found(request: Request, exc: StarletteHTTPException) -> Response:
        return HTMLResponse(render_not_found(fleet, config), status_code=exc.status_code)

    app.mount("/", StaticFiles(directory=PUBLIC_DIR), name="public")
    return app
