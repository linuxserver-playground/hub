"""The built site: every documented path is built, the spec is valid, and the files land where they should."""

from collections.abc import Hashable, Mapping
from pathlib import Path
from typing import Any, cast

import pytest
import yaml
from fastapi.testclient import TestClient
from openapi_spec_validator import validate

from lsio_hub.app import create_app
from lsio_hub.build import render, route_paths, write_site
from lsio_hub.config import SiteConfig
from lsio_hub.fleet import Fleet, load_fleet
from lsio_hub.store import Store


def test_builds_every_documented_path(fleet: Fleet, spec: dict[str, Any], files: dict[str, bytes]) -> None:
    for path in spec["paths"]:
        if "{" not in path:
            assert path.lstrip("/") in files, path
    for image in fleet.images:
        assert f"api/v1/catalog/{image.name}.json" in files
        assert f"api/v1/catalog/{image.name}/docker-compose.yml" in files
        assert f"api/v1/catalog/{image.name}/builds.json" in files
        assert f"api/v1/catalog/{image.name}/mods.json" in files
    assert {"index.html", "404.html", "openapi.json", "openapi.yaml"} <= files.keys()


def test_per_build_files(files: dict[str, bytes]) -> None:
    base = "api/v1/catalog/sonarr/builds/4.0.20.3014-ls2"
    assert {
        f"{base}.json",
        f"{base}/diff.json",
        f"{base}/layers.amd64.json",
        f"{base}/packages.arm64.json",
    } <= files.keys()
    assert f"{base}/tests.json" in files and f"{base}/report.json" in files
    assert f"{base}/vulns.json" in files and "api/v1/catalog/sonarr/builds/4.0.19.2000-ls1/vulns.json" not in files
    assert "api/v1/catalog/sonarr/builds/4.0.19.2000-ls1/packages.amd64.json" not in files
    assert "api/v1/catalog/multidb/builds/1.0.0-ls1/layers.arm64.json" not in files  # arm64 failed
    assert "api/v1/catalog/multidb/builds/1.0.0-ls1/layers.amd64.json" in files


def test_generated_documents_only_where_enabled(files: dict[str, bytes]) -> None:
    assert "api/v1/catalog/sonarr/proxy.json" in files and "api/v1/catalog/swag/proxy.json" not in files
    assert "api/v1/catalog/multidb/kubernetes.yaml" in files
    assert "api/v1/catalog/swag/quadlet.container" in files
    assert "api/v1/packages/curl.json" in files and "api/v1/packages.json" in files
    assert files["api/v1/catalog/sonarr/quadlet.container"].startswith(b"# sonarr.container")


def test_route_paths_need_values_for_every_parameter(fleet: Fleet, config: SiteConfig) -> None:
    app = create_app(fleet, config)

    @app.get("/api/v1/categories/{category}.json")
    def category(category: str) -> str:
        return category

    with pytest.raises(ValueError, match="no values to build category"):
        route_paths(app, fleet)


def test_spec_is_valid_openapi(spec: dict[str, Any], files: dict[str, bytes]) -> None:
    validate(cast(Mapping[Hashable, Any], spec))
    assert spec["servers"] == [{"url": "https://example.github.io/hub"}]
    assert yaml.safe_load(files["openapi.yaml"]) == spec
    assert "422" not in str(spec["paths"]["/api/v1/catalog/{name}.json"]["get"]["responses"])


def test_operation_ids_are_unique_and_tagged(spec: dict[str, Any]) -> None:
    ops = [item["get"] for item in spec["paths"].values()]
    ids = [op["operationId"] for op in ops]
    assert len(set(ids)) == len(ids)
    tags = {t["name"] for t in spec["tags"]}
    assert all(set(op["tags"]) <= tags for op in ops)


def test_extensionless_compat_files_match_their_json_twins(files: dict[str, bytes]) -> None:
    assert files["health"] == files["health.json"] == b'"Success"'
    assert files["api/v1/images"] == files["api/v1/images.json"]


def test_compose_yaml_feed(files: dict[str, bytes]) -> None:
    compose = yaml.safe_load(files["api/v1/catalog/sonarr/docker-compose.yml"])
    assert compose["services"]["sonarr"]["restart"] == "unless-stopped"
    assert list(yaml.safe_load_all(files["api/v1/catalog/multidb/kubernetes.yaml"]))[-1]["kind"] == "Service"
    feed = files["api/v1/changelog.xml"].decode()
    assert feed.startswith('<?xml version="1.0" encoding="utf-8"?>') and feed.endswith("</feed>\n")


def test_unknown_paths_get_the_404_page(client: TestClient, files: dict[str, bytes]) -> None:
    for path in (
        "/api/v1/catalog/nope.json",
        "/api/v1/catalog/sonarr/builds/nope.json",
        "/api/v1/catalog/swag/proxy.json",
        "/nope",
    ):
        res = client.get(path)
        assert res.status_code == 404, path
        assert res.content == files["404.html"]


def test_writes_files_and_public_assets(tmp_path: Path, files: dict[str, bytes]) -> None:
    write_site(tmp_path, files)
    assert (tmp_path / "api/v1/images").read_bytes() == (tmp_path / "api/v1/images.json").read_bytes()
    for asset in ("assets/site.css", "assets/site.js", "favicon.svg", "index.html", "404.html"):
        assert (tmp_path / asset).stat().st_size > 0


def test_failed_manifest_refresh_reports_failed(store: Store, config: SiteConfig) -> None:
    store.status["sources"]["manifests"] = {"ok": False, "checked_at": "2026-10-25T04:00:00Z", "error": "down"}
    assert render(load_fleet(store, config), config)["health"] == b'"Failed"'


def test_tests_json_only_for_builds_with_a_report(store: Store, config: SiteConfig) -> None:
    store.images["swag"].tests.clear()
    files = render(load_fleet(store, config), config)
    assert "api/v1/catalog/swag/builds/5.2.0-ls1/tests.json" not in files
    assert "api/v1/catalog/swag/builds/5.2.0-ls1/report.json" in files
    assert "api/v1/catalog/sonarr/builds/4.0.20.3014-ls2/tests.json" in files


def test_report_and_tests_bodies(client: TestClient) -> None:
    report = client.get("/api/v1/catalog/sonarr/builds/4.0.20.3014-ls2/report.json").json()["data"]["report"]
    assert report["result"] == "success" and report["tests"]["amd64"]["listening_ports"] == ["8989/tcp"]
    assert "null" not in str(report["diff"]["upstream"])  # None is dropped, as everywhere else
    tests = client.get("/api/v1/catalog/sonarr/builds/4.0.20.3014-ls2/tests.json").json()["data"]
    assert tests["reports"]["amd64"]["schema"] == 1 and tests["summary"]["arm64"]["success"] is True
    layers = client.get("/api/v1/catalog/sonarr/builds/4.0.20.3014-ls2/layers.amd64.json").json()["data"]
    assert layers["from_base_source"] == "registry" and layers["layers"][1]["dockerfile_lines"] == [2, 2]
    assert client.get("/api/v1/catalog/sonarr/builds/nope/report.json").status_code == 404


def test_build_json_is_the_bundle_as_received(client: TestClient, store: Store) -> None:
    body = client.get("/api/v1/catalog/sonarr/builds/4.0.20.3014-ls2.json").json()
    assert body["data"]["build"] == store.images["sonarr"].builds["4.0.20.3014-ls2"]
