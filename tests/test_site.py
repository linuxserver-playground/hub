import re
from dataclasses import replace
from typing import Any

from lsio_hub.config import SiteConfig
from lsio_hub.fleet import Fleet
from lsio_hub.site import operation_groups, render_not_found
from lsio_hub.templating import compact, format_timestamp

PAGE_FILES = ("index.html", "404.html")


def test_documents_every_operation(spec: dict[str, Any], files: dict[str, bytes]) -> None:
    page = files["index.html"].decode()
    for path, item in spec["paths"].items():
        assert f'id="op-{item["get"]["operationId"]}"' in page
        assert f'data-path="{path}"' in page


def test_local_links_use_the_base_path(files: dict[str, bytes]) -> None:
    for name in PAGE_FILES:
        local = re.findall(r'(?:href|src)="(/[^"]*)"', files[name].decode())
        assert local
        assert all(url.startswith("/hub/") for url in local), name


def test_shows_real_data(fleet: Fleet, files: dict[str, bytes]) -> None:
    page = files["index.html"].decode()
    assert "API=https://example.github.io/hub/api/v1" in page and "$API/catalog/sonarr.json" in page
    assert '<span class="out">4.0.20.3014-ls2</span>' in page
    assert '<option value="swag">' in page
    assert "image.yml on every live branch" in page
    assert "builds/4.0.20.3014-ls2/layers.amd64.json" in page and "packages/curl.json" in page


def test_says_when_the_last_refresh_failed(fleet: Fleet, config: SiteConfig) -> None:
    page = render_not_found(replace(fleet, health="Failed"), config)
    assert "Last refresh failed" in page and "pulse-bad" in page


def test_one_h1_and_labelled_landmarks(files: dict[str, bytes]) -> None:
    for name in PAGE_FILES:
        page = files[name].decode()
        assert len(re.findall(r"<h1[\s>]", page)) == 1
        assert '<main id="main"' in page and '<nav aria-label="Main"' in page


def test_groups_follow_the_spec_tags(spec: dict[str, Any]) -> None:
    groups = operation_groups(spec, SiteConfig(), {"name": "sonarr"})
    assert [tag["name"] for tag, _ in groups] == [t["name"] for t in spec["tags"]]
    assert all(ops for _, ops in groups)


def test_formatting() -> None:
    assert compact(17_321_271_697) == "17.3B"
    assert compact(999_999) == "1M"
    assert format_timestamp("2026-10-24T13:11:46.000Z") == "24 Oct 2026, 13:11 UTC"
    assert format_timestamp("") == "never"
