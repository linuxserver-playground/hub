"""v1 fields from the manifest and the builds, as the original API shaped them."""

import json

from lsio_hub.config import SiteConfig
from lsio_hub.fleet import Fleet, hub_settings, load_fleet
from lsio_hub.responses import to_v1_image
from lsio_hub.store import Store
from lsio_hub.transform import build_image

from .conftest import FIXTURES

LIVE = json.loads((FIXTURES / "live-v1-sonarr.json").read_text())


def test_v1_keys_in_the_original_order(fleet: Fleet) -> None:
    sonarr = next(i for i in fleet.images if i.name == "sonarr")
    v1 = to_v1_image(sonarr, include_config=True).model_dump(exclude_none=True)
    expected = [k for k in LIVE if k != "monthly_pulls"]  # the playground has no pull counts
    assert list(v1) == expected
    assert [k for k in LIVE["config"]] == [k for k in v1["config"] if k in LIVE["config"]]
    assert "monthly_pulls" not in v1


def test_version_fields_come_from_the_latest_branch_build(fleet: Fleet) -> None:
    sonarr = fleet.image("sonarr")
    assert sonarr is not None
    assert sonarr.version == "4.0.20.3014-ls2"
    assert sonarr.upstream_version == "4.0.20.3014"
    assert sonarr.version_timestamp == "2026-10-20 19:16:08+00:00"
    assert sonarr.release_url == "https://github.com/linuxserver-playground/docker-sonarr/releases/tag/4.0.20.3014-ls2"
    assert [r.release_tag for r in sonarr.releases] == ["develop", "latest"]
    assert sonarr.releases[0].tag == "develop-5.0.1.1234-ls1" and sonarr.releases[0].channel == "prerelease"


def test_manifest_mapping(fleet: Fleet) -> None:
    sonarr = fleet.image("sonarr")
    assert sonarr is not None
    assert sonarr.category == "Media Management"
    assert sonarr.description.startswith("[Sonarr](https://sonarr.tv/) (formerly NZBdrone)")
    assert [t.model_dump() for t in sonarr.tags] == [
        {"tag": "latest", "desc": "Stable releases from Sonarr"},
        {"tag": "develop", "desc": "Development releases from Sonarr"},
    ]
    assert [a.model_dump() for a in sonarr.architectures] == [
        {"arch": "x86_64", "tag": "amd64-latest"},
        {"arch": "arm64", "tag": "arm64v8-latest"},
    ]
    assert sonarr.stable and not sonarr.deprecated and sonarr.stars == 7
    assert sonarr.initial_date == "2015-08-31"
    assert sonarr.changelog is not None and sonarr.changelog[0].date == "2026-10-19"
    assert sonarr.project_logo and sonarr.project_logo.endswith("sonarr-banner.png")
    assert sonarr.github_url == "https://github.com/linuxserver-playground/docker-sonarr"
    assert sonarr.registries.ghcr == "ghcr.io/linuxserver-playground/sonarr"
    assert sonarr.docs_url == "https://linuxserver-playground.github.io/site/images/sonarr/"
    assert sonarr.links.proxy and sonarr.links.kubernetes and sonarr.links.quadlet
    assert sonarr.snippets.docker_compose.startswith("---\nservices:\n  sonarr:\n")
    assert "image: ghcr.io/linuxserver-playground/sonarr:latest" in sonarr.snippets.docker_compose


def test_config_mapping(fleet: Fleet) -> None:
    config = fleet.image("multidb").config  # type: ignore[union-attr]
    assert config.application_setup is not None and config.application_setup.endswith("#application-setup")
    assert config.readonly_supported is False and config.nonroot_supported is True
    assert config.privileged is True  # "optional" counts as privileged, as the original's bool did
    assert config.networking == "bridge"
    assert config.hostname is not None and config.hostname.optional
    assert config.env_vars is not None
    assert [e.name for e in config.env_vars] == [
        "PUID",
        "PGID",
        "TZ",
        "DB_HOST",
        "DB_PASS",
        "LOG_LEVEL",
        "FEATURE_FLAG",
    ]
    assert config.env_vars[0].desc == "User ID" and config.env_vars[-1].optional
    assert config.ports is not None and config.ports[1].internal == "1900/udp" and config.ports[1].optional
    assert config.volumes is not None and config.volumes[0].host_path == "/path/to/multidb/config"
    assert config.volumes[1].host_path == "/path/to/multidb/media"  # the manifest default
    assert config.custom is not None and config.custom[0].model_dump() == {
        "name": "shm-size",
        "name_compose": "shm_size",
        "value": "1gb",
        "desc": "Shared memory for the browser",
        "optional": False,
    }
    assert config.custom[1].value == ["net.ipv4.ip_forward=1"]
    assert config.security_opt is not None and config.security_opt[0].compose_var == "seccomp:unconfined"
    assert config.devices is not None and config.devices[0].host_path == "/dev/dri"
    assert config.caps is not None and config.caps[0].cap_add == "NET_ADMIN"
    swag = fleet.image("swag").config  # type: ignore[union-attr]
    assert swag.readonly_supported is True and swag.nonroot_supported is None and swag.privileged is None


def test_image_without_builds_falls_back_like_the_original(store: Store, config: SiteConfig) -> None:
    sonarr = store.images["sonarr"]
    sonarr.builds.clear()
    sonarr.latest.clear()
    image = build_image(sonarr, {"pushed_at": "2026-10-23T00:00:00Z", "stars": 1}, hub_settings(config), config, None)
    assert image is not None
    assert image.version == "latest" and image.version_timestamp == "2026-10-23 00:00:00+00:00"
    assert image.releases[1].tag is None
    bare = build_image(sonarr, {}, hub_settings(config), config, None)
    assert bare is not None and bare.version_timestamp == "1970-01-01 00:00:00+00:00"


def test_deprecated_image(store: Store, config: SiteConfig) -> None:
    manifest = store.images["swag"].manifests["master"]
    manifest["deprecation"] = {"status": True, "message": "Use something else."}
    fleet = load_fleet(store, config)
    swag = fleet.image("swag")
    assert swag is not None and swag.deprecated and swag.deprecation_message == "Use something else."
    assert "swag" not in [i.name for i in fleet.current]


def test_broken_record_is_skipped(store: Store, config: SiteConfig) -> None:
    store.images["swag"].manifests["master"]["runtime"] = "broken"
    assert [i.name for i in load_fleet(store, config).images] == ["multidb", "sonarr"]


def test_archived_comes_from_observed(fleet: Fleet) -> None:
    assert fleet.image("multidb").archived is True  # type: ignore[union-attr]
    assert fleet.image("sonarr").archived is False  # type: ignore[union-attr]
