"""Each endpoint's content, built without HTTP."""

from lsio_hub import responses
from lsio_hub.fleet import Fleet
from lsio_hub.models import CHANGELOG_LIMIT


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
    assert status.health == "Success" and set(status.sources) == {"manifests", "releases", "observed", "mods"}
    assert sorted(status.rejected) == ["multidb@bad-ls9", "multidb@feature-ls1"]


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
    assert newest.links.files["amd64"].endswith("files.amd64.json.gz")
    assert [h.tag for h in data.history["master"]] == ["4.0.20.3014-ls2", "4.0.19.2000-ls1"]
    bundle = responses.bundle(sonarr, "4.0.20.3014-ls2")
    assert bundle is not None and bundle.schema_version == 1 and bundle.model_dump(by_alias=True)["schema"] == 1
    assert responses.bundle(sonarr, "nope") is None
    assert responses.layers(sonarr, "4.0.20.3014-ls2", "amd64").layers[0].from_base is True  # type: ignore[union-attr]
    table = responses.packages_table(sonarr, "4.0.20.3014-ls2", "amd64")
    assert table is not None and table.count == 4 and table.packages[0].licenses == ["MIT"]
    assert responses.packages_table(sonarr, "4.0.19.2000-ls1", "amd64") is None


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
    assert mods.source.startswith("legacy linuxserver/docker-mods")
    assert len(mods.mods) == 88
    sonarr = responses.image_mods(fleet, "sonarr").mods
    assert sonarr[0].name == "striptracks" and sonarr[0].target == "radarr" and "sonarr" in sonarr[0].applies_to
    assert all(m.target == "universal" for m in sonarr[1:]) and len(sonarr) == 13
    assert sonarr[0].image == "ghcr.io/linuxserver/mods:radarr-striptracks"


def test_proxy_kubernetes_quadlet(fleet: Fleet) -> None:
    proxy = responses.proxy_data(fleet, "sonarr")
    assert proxy is not None and proxy.subdomain and proxy.subfolder and proxy.port == 8989
    assert proxy.base_url_note is not None and proxy.base_url_note.startswith("Settings")
    assert responses.proxy_data(fleet, "swag") is None
    assert responses.kubernetes_yaml(fleet, "sonarr") is not None
    assert responses.quadlet_unit(fleet, "swag") is not None
    assert responses.names_with(fleet, "proxy") == ["multidb", "sonarr"]
    assert responses.names_with(fleet, "kubernetes") == ["multidb", "sonarr", "swag"]


def test_stores_index(fleet: Fleet) -> None:
    stores = responses.stores_index(fleet)
    assert {s.platform for s in stores} >= {
        "unraid",
        "portainer",
        "casaos",
        "umbrel",
        "runtipi",
        "cosmos",
        "proxy",
        "kubernetes",
        "quadlet",
        "mods",
        "builds",
        "docs",
    }
    assert (
        next(s for s in stores if s.platform == "portainer").url
        == "https://example.github.io/hub/stores/portainer/templates.json"
    )
    assert all(s.how_to for s in stores)
