"""Each endpoint's content, built without HTTP."""

import yaml

from lsio_hub import responses
from lsio_hub.config import SiteConfig
from lsio_hub.fleet import Fleet, load_fleet
from lsio_hub.models import CHANGELOG_LIMIT
from lsio_hub.store import Store


def test_images_response_envelope(fleet: Fleet) -> None:
    res = responses.images_response(fleet)
    assert res.status == "OK" and res.last_updated == "2026-10-24 12:00:00+00:00"
    names = [i.name for i in res.data.repositories.linuxserver]
    assert names == ["multidb", "sonarr", "swag"]
    assert all(i.config is None for i in res.data.repositories.linuxserver)
    with_config = responses.images_response(fleet, include_config=True).data.repositories.linuxserver
    assert all(i.config is not None for i in with_config)


def test_categories_and_stats(fleet: Fleet) -> None:
    cats = responses.categories(fleet)
    assert [c.name for c in cats] == ["Databases", "Media Management", "Media Servers", "Reverse Proxy"]
    assert cats[2].model_dump() == {"name": "Media Servers", "slug": "media-servers", "count": 1, "images": ["multidb"]}
    stats = responses.stats(fleet)
    assert stats.images == 3 and stats.deprecated == 0 and stats.stars == 7 and stats.builds == 6
    assert stats.architectures == {"x86_64": 3, "arm64": 3}
    assert stats.readonly_supported == 2 and stats.nonroot_supported == 2
    assert stats.updated_last_7_days == 3 and stats.categories == 4 and stats.first_release == "2015-08-31"


def test_base_images_and_tools_are_catalog_only(store: Store, config: SiteConfig) -> None:
    store.images["multidb"].manifests["master"]["kind"] = "base"
    store.images["swag"].manifest["kind"] = "tool"  # type: ignore[index]
    fleet = load_fleet(store, config)
    assert {i.name: i.kind for i in fleet.images} == {"multidb": "base", "sonarr": "app", "swag": "tool"}
    assert [i.name for i in responses.images_response(fleet).data.repositories.linuxserver] == ["sonarr"]
    assert [c.name for c in responses.categories(fleet)] == ["Media Management"]
    stats = responses.stats(fleet)
    assert (stats.images, stats.base_images, stats.tools, stats.deprecated) == (1, 1, 1, 0)
    assert responses.kubernetes_yaml(fleet, "swag") is None and responses.proxy_data(fleet, "swag") is None
    assert responses.names_with(fleet, "quadlet") == ["sonarr"]
    swag = fleet.image("swag")
    assert swag is not None and swag.links.kubernetes is None and swag.links.proxy is None


def test_changelog_newest_first(fleet: Fleet) -> None:
    entries = responses.recent_changelog(fleet)
    assert len(entries) <= CHANGELOG_LIMIT
    assert entries[0].date >= entries[-1].date
    assert entries[0].model_dump() == {
        "image": "swag",
        "date": "2026-10-20",
        "desc": entries[0].desc,
    }


def test_status_includes_rejected(fleet: Fleet) -> None:
    status = responses.status(fleet)
    assert status.health == "Success" and set(status.sources) == {
        "manifests",
        "releases",
        "observed",
        "mods",
        "vulnerabilities",
    }
    assert sorted(status.rejected) == ["multidb@bad-ls9", "multidb@feature-ls1"]
    assert status.sources["observed"].fetched_at == fleet.store.observed["fetched_at"]


def test_status_observed_fetched_at_comes_from_observed_json(store: Store, config: SiteConfig) -> None:
    store.observed["fetched_at"] = "2026-10-25T01:00:00.000Z"
    store.status["sources"]["observed"] = {"ok": False, "checked_at": "2026-10-25T02:00:00.000Z", "error": "down"}
    status = responses.status(load_fleet(store, config))
    observed = status.sources["observed"]
    assert observed.ok is False and observed.fetched_at == "2026-10-25T01:00:00.000Z" and observed.error == "down"


def test_builds(fleet: Fleet) -> None:
    sonarr = fleet.record("sonarr")
    assert sonarr is not None
    data = responses.builds(fleet, sonarr)
    assert [b.tag for b in data.builds] == ["develop-5.0.1.1234-ls1", "4.0.20.3014-ls2", "4.0.19.2000-ls1"]
    newest = data.builds[1]
    assert newest.classification == "upstream" and newest.test_success is True
    assert newest.links.packages == {
        "amd64": "https://example.github.io/hub/api/v1/catalog/sonarr/builds/4.0.20.3014-ls2/packages.amd64.json",
        "arm64": "https://example.github.io/hub/api/v1/catalog/sonarr/builds/4.0.20.3014-ls2/packages.arm64.json",
    }
    assert data.builds[2].links.packages == {}  # only the newest build of a branch keeps its table
    assert newest.links.test_report == "https://example.github.io/hub/builds/sonarr/4.0.20.3014-ls2/"
    # The newest build of a branch has its file trees copied next to the report page: same origin as the API.
    assert newest.links.files == {
        "amd64": "https://example.github.io/hub/builds/sonarr/4.0.20.3014-ls2/files.amd64.json.gz",
        "arm64": "https://example.github.io/hub/builds/sonarr/4.0.20.3014-ls2/files.arm64.json.gz",
    }
    assert newest.links.files_release["amd64"] == "https://assets.test/sonarr/4.0.20.3014-ls2/files.amd64.json.gz"
    older = data.builds[2]
    assert older.links.files == older.links.files_release
    assert older.links.files["amd64"] == "https://assets.test/sonarr/4.0.19.2000-ls1/files.amd64.json.gz"
    assert newest.links.tests == "https://example.github.io/hub/api/v1/catalog/sonarr/builds/4.0.20.3014-ls2/tests.json"
    assert (
        newest.links.report == "https://example.github.io/hub/api/v1/catalog/sonarr/builds/4.0.20.3014-ls2/report.json"
    )
    assert newest.links.vulns == "https://example.github.io/hub/api/v1/catalog/sonarr/builds/4.0.20.3014-ls2/vulns.json"
    assert newest.vulnerabilities is not None and newest.vulnerabilities.critical == 1
    assert data.builds[2].vulnerabilities is None and data.builds[2].links.vulns is None
    assert [h.tag for h in data.history["master"]] == ["4.0.20.3014-ls2", "4.0.19.2000-ls1"]
    bundle = responses.bundle(sonarr, "4.0.20.3014-ls2")
    assert bundle is not None and bundle.schema_version == 1 and bundle.model_dump(by_alias=True)["schema"] == 1
    assert responses.bundle(sonarr, "nope") is None
    assert responses.layers(sonarr, "4.0.20.3014-ls2", "amd64").layers[0].from_base is True  # type: ignore[union-attr]
    assert responses.layers(sonarr, "nope", "amd64") is None
    table = responses.packages_table(sonarr, "4.0.20.3014-ls2", "amd64")
    assert table is not None and table.count == 4 and table.packages[0].licenses == ["MIT"]
    assert responses.packages_table(sonarr, "4.0.19.2000-ls1", "amd64") is None


def test_layers_are_attributed(fleet: Fleet) -> None:
    sonarr = fleet.record("sonarr")
    assert sonarr is not None
    layers = responses.layers(sonarr, "4.0.20.3014-ls2", "arm64", fleet.store.bases)
    assert layers is not None and layers.base_layers == 1 and layers.from_base_source == "registry"
    assert [(x.from_base, x.dockerfile_lines) for x in layers.layers] == [
        (True, None),
        (False, [2, 2]),
        (False, [3, 3]),
    ]
    multidb = fleet.record("multidb")
    assert multidb is not None
    # multidb's base is not in data/bases/ (the registry fixture answers 404): the harness's flags stand, and the
    # RUN changed to `apk add curl jq` so its created_by no longer matches.
    layers = responses.layers(multidb, "1.0.0-ls2", "amd64", fleet.store.bases)
    assert layers is not None and layers.from_base_source == "harness" and layers.base_layers == 1
    assert [(x.from_base, x.dockerfile_lines) for x in layers.layers] == [(True, None), (False, None), (False, [3, 3])]


def test_tests_and_report(fleet: Fleet) -> None:
    multidb = fleet.record("multidb")
    assert multidb is not None
    tests = responses.tests(fleet, multidb, "1.0.0-ls1")
    assert tests is not None and tests.enabled and tests.success is False
    assert tests.report_url == "https://example.github.io/hub/builds/multidb/1.0.0-ls1/"
    assert sorted(tests.reports) == ["amd64", "arm64"] and tests.reports["arm64"].tests[2].status == "FAIL"
    arm64 = tests.summary["arm64"]
    assert (
        arm64.success is False and arm64.failed_tests == ["Take screenshot"] and (arm64.passed, arm64.total) == (2, 3)
    )
    assert arm64.startup_seconds == 4.2 and arm64.listening_ports == ["8989/tcp"] and arm64.warnings == 1
    assert tests.summary["amd64"].success is True and tests.summary["amd64"].failed_tests == []
    assert responses.tests(fleet, multidb, "nope") is None
    assert responses.test_routes(fleet)[:2] == [("multidb", "1.0.0-ls1"), ("multidb", "1.0.0-ls2")]

    report = responses.report(fleet, multidb, "1.0.0-ls2")
    assert (
        report is not None
        and report.result == "success"
        and report.is_newest
        and report.classification == "linuxserver"
    )
    assert (
        report.diff is not None
        and report.diff.previous_tag == "1.0.0-ls1"
        and report.diff.dockerfile_changed == ["amd64", "arm64"]
    )
    assert report.diff.config_changes == 1 and report.diff.totals.upgraded == 1 and not report.diff.base_changed
    assert report.tests["arm64"].success is False and report.links.run.endswith("/actions/runs/1002")
    assert report.links.registry == "ghcr.io/linuxserver-playground/multidb:1.0.0-ls2"
    assert report.links.history == "https://example.github.io/hub/builds/multidb/"
    assert report.links.files["amd64"].startswith("https://example.github.io/hub/builds/multidb/1.0.0-ls2/")
    first = responses.report(fleet, multidb, "1.0.0-ls1")
    assert (
        first is not None
        and first.result == "failure"
        and not first.is_newest
        and first.tags == ["latest", "1.0.0-ls1"]
    )
    assert first.diff is not None and first.diff.classification == "initial"
    swag = fleet.record("swag")
    assert swag is not None
    disabled = responses.report(fleet, swag, "5.2.0-ls1")
    assert disabled is not None and disabled.test_enabled is False and disabled.test_success is None
    assert disabled.result == "success"
    assert responses.report(fleet, multidb, "nope") is None


def test_build_result() -> None:
    assert (
        responses.build_result({"platforms": [{"result": "success"}, {"result": "failure"}], "test": {"success": True}})
        == "partial"
    )
    assert responses.build_result({"platforms": [{"result": "failure"}], "test": {"enabled": False}}) == "failure"
    assert (
        responses.build_result({"platforms": [{"result": "success"}], "test": {"enabled": True, "success": False}})
        == "failure"
    )


def test_packages_index_and_detail(fleet: Fleet) -> None:
    index = responses.package_index(fleet)
    curl = next(e for e in index if e.name == "curl")
    assert curl.images == 3 and curl.types == ["apk"] and curl.slug == "curl"
    detail = responses.package_detail(fleet, "curl")
    assert detail is not None
    assert detail.images == ["multidb", "sonarr", "swag"]
    assert detail.versions == ["8.9.1-r0", "8.9.0-r0"]
    assert {(h.image, h.branch) for h in detail.holders} == {
        ("multidb", "master"),
        ("sonarr", "master"),
        ("sonarr", "develop"),
        ("swag", "master"),
    }
    assert responses.package_detail(fleet, "nope") is None
    assert "Sonarr" in [e.name for e in index]


def test_bases_and_staleness(fleet: Fleet) -> None:
    bases = responses.bases(fleet).bases
    assert len(bases) == 1
    base = bases[0]
    assert base.image == "ghcr.io/linuxserver/baseimage-alpine:3.24" and base.images == ["multidb", "sonarr", "swag"]
    assert len(base.digests) == 2  # the b...b digest and multidb's e...e digest
    stale = responses.staleness(fleet)
    assert stale.checked == 4
    # multidb's newest build (23 Oct) is newer than any other digest sighting, so nothing is stale yet.
    assert stale.stale == []


def test_staleness_flags_an_older_digest(fleet: Fleet) -> None:
    swag = fleet.record("swag")
    assert swag is not None
    build = swag.builds["5.2.0-ls1"]
    build["created"] = "2026-09-01T00:00:00Z"
    build["base"]["digest"] = "sha256:" + "0" * 64
    stale = responses.staleness(fleet).stale
    assert [s.image for s in stale] == ["swag"]
    assert stale[0].newest_base_digest == "sha256:" + "e" * 64


def test_mods(fleet: Fleet) -> None:
    mods = responses.mods(fleet)
    assert mods.source.startswith("mod.yml on each branch of linuxserver-playground/docker-mods")
    assert len(mods.mods) == 6 and {m.source for m in mods.mods} == {"playground"}
    sonarr = [m.branch for m in responses.image_mods(fleet, "sonarr").mods]
    # Its own (listed) mods, then universal mods curated for it (none here), then every other universal mod.
    assert sonarr == ["radarr-striptracks", "universal-calibre", "universal-docker", "universal-git"]
    code = [m.branch for m in responses.image_mods(fleet, "openvscode-server").mods]
    assert code == ["code-server-python3-poetry", "universal-docker", "universal-calibre", "universal-git"]


def test_mods_without_a_source_are_playground_mods(store: Store, config: SiteConfig) -> None:
    """data/mods.json written before entries carried `source`."""
    for mod in store.mods["mods"]:
        mod.pop("source", None)
    assert {m.source for m in load_fleet(store, config).mods} == {"playground"}


def test_proxy_kubernetes_quadlet(fleet: Fleet) -> None:
    proxy = responses.proxy_data(fleet, "sonarr")
    assert proxy is not None and proxy.subdomain and proxy.subfolder and proxy.port == 8989
    assert proxy.base_url_note is not None and proxy.base_url_note.startswith("Settings")
    assert responses.proxy_data(fleet, "swag") is None
    assert responses.kubernetes_yaml(fleet, "sonarr") is not None
    assert responses.quadlet_unit(fleet, "swag") is not None
    assert responses.names_with(fleet, "proxy") == ["multidb", "sonarr"]
    assert responses.names_with(fleet, "kubernetes") == ["multidb", "sonarr", "swag"]


def test_caddy_and_traefik_references(fleet: Fleet) -> None:
    """Checked by hand against caddy adapt and a Traefik 3.7 docker provider; these pin the shape."""
    proxy = responses.proxy_data(fleet, "sonarr")
    assert proxy is not None and proxy.caddy and proxy.traefik
    caddy = proxy.caddy
    assert "sonarr.example.com {\n" in caddy and "\t@api path /api /api/*\n" in caddy
    assert caddy.count("\n\t\treverse_proxy sonarr:8989\n") == 2  # the open API route and the main one
    assert "# forward_auth authelia:9091 {" in caddy and "\n# example.com {\n" in caddy  # subfolder, commented
    assert "@api path /sonarr/api /sonarr/api/*" in caddy and "Settings → General → URL Base" in caddy
    traefik = yaml.safe_load(proxy.traefik)["services"]["sonarr"]["labels"]
    assert "traefik.http.routers.sonarr.rule=Host(`sonarr.example.com`)" in traefik
    assert "traefik.http.services.sonarr.loadbalancer.server.port=8989" in traefik
    assert "traefik.http.routers.sonarr-api.rule=Host(`sonarr.example.com`) && (PathPrefix(`/api`))" in traefik
    assert "# - traefik.http.routers.sonarr.middlewares=authelia@docker" in proxy.traefik
    assert not any("middlewares" in label for label in traefik)  # authentication stays commented

    multidb = responses.proxy_data(fleet, "multidb")
    assert multidb is not None and multidb.caddy and multidb.traefik
    assert "reverse_proxy https://multidb:8080 {\n" in multidb.caddy and "tls_insecure_skip_verify" in multidb.caddy
    assert "@api path /api /api/* /ws /ws/*" in multidb.caddy and "handle /metrics* {" in multidb.caddy
    assert "reverse_proxy multidb:9090" in multidb.caddy and "example.com {\n#" not in multidb.caddy  # no subfolder
    labels = yaml.safe_load(multidb.traefik)["services"]["multidb"]["labels"]
    assert "traefik.http.services.multidb.loadbalancer.server.scheme=https" in labels
    assert "traefik.http.services.multidb-extra1.loadbalancer.server.port=9090" in labels
    assert "traefik.http.routers.multidb-extra1.service=multidb-extra1" in labels


def test_stores_index(fleet: Fleet) -> None:
    stores = responses.stores_index(fleet)
    assert [s.platform for s in stores] == ["unraid", "portainer", "casaos", "umbrel", "runtipi", "cosmos", "arcane"]
    urls = {s.platform: s.url for s in stores}
    assert urls["portainer"] == "https://example.github.io/hub/stores/portainer/templates.json"
    assert urls["unraid"] == "https://github.com/linuxserver-playground/unraid-store"
    assert urls["umbrel"] == "https://github.com/linuxserver-playground/umbrel-store"
    assert all(s.how_to for s in stores)


def test_doc_sections_split_at_level_two_headings_outside_code() -> None:
    text = (
        "# Title\n\nbadges\n\n## Application Setup\n\nRun it.\n\n### Media folders\n\nKeep them.\n\n"
        "## Usage\n\n```yaml\n## not a heading\n```\n"
    )
    sections = responses.doc_sections(text)
    assert [(s.id, s.title) for s in sections] == [("application-setup", "Application Setup"), ("usage", "Usage")]
    assert "### Media folders" in sections[0].markdown and "## not a heading" in sections[1].markdown
    assert responses.doc_sections("no sections at all") == []


def test_docs_data_is_the_full_readme(fleet: Fleet) -> None:
    docs = responses.docs_data(fleet, "sonarr")
    assert docs is not None
    ids = [s.id for s in docs.sections]
    for wanted in (
        "application-setup",
        "usage",
        "parameters",
        "user-group-identifiers",
        "support-info",
        "updating-info",
        "building-locally",
    ):
        assert wanted in ids, (wanted, ids)
    assert responses.docs_data(fleet, "nope") is None
