"""The diff engine, on constructed bundles."""

import copy

from lsio_hub.diff import classify, diff_builds, dockerfile_diff, package_diff
from lsio_hub.models import Diff
from lsio_hub.packages import compare_versions, normalise, slug, version_key

from .conftest import MULTIDB_LS1, MULTIDB_LS2, SONARR_LS1, SONARR_LS2, bundle, syft_document

OLD = [{"name": "curl", "version": "8.9.0-r0", "type": "apk", "purl": "pkg:apk/curl@8.9.0-r0"}]
NEW = [{"name": "curl", "version": "8.9.1-r0", "type": "apk", "purl": "pkg:apk/curl@8.9.1-r0"}]


def test_upstream_change_with_package_upgrades() -> None:
    diff = diff_builds(SONARR_LS2, SONARR_LS1, {"amd64": NEW}, {"amd64": OLD})
    assert diff["classification"] == "upstream"
    assert diff["upstream"] == {"from": "4.0.19.2000", "to": "4.0.20.3014", "changed": True}
    assert diff["packages"]["amd64"]["apk"]["upgraded"] == [
        {"name": "curl", "from": "8.9.0-r0", "to": "8.9.1-r0", "purl": "pkg:apk/curl@8.9.1-r0"}
    ]
    assert diff["totals"] == {"added": 0, "removed": 0, "upgraded": 1, "downgraded": 0}
    assert diff["size"]["amd64"]["delta"] == 1000
    Diff.model_validate(diff)


def test_dockerfile_change_is_linuxserver() -> None:
    diff = diff_builds(MULTIDB_LS2, MULTIDB_LS1, None, None)
    assert diff["classification"] == "linuxserver"
    assert diff["dockerfile"]["amd64"].startswith("--- a/Dockerfile\n+++ b/Dockerfile\n")
    assert "+RUN apk add curl jq" in diff["dockerfile"]["amd64"]
    assert diff["dockerfile"]["arm64"].startswith("--- a/Dockerfile.aarch64")
    assert diff["config"]["env"] == {"added": ["NEW_VAR"], "removed": [], "changed": []}
    assert diff["packages"] is None  # no tables given
    assert diff["size"]["arm64"] == {"from": None, "to": 48_002_000, "delta": None}


def test_push_without_dockerfile_change_is_linuxserver() -> None:
    old = bundle("x", "master", "1.0", 1, "2026-10-01T00:00:00Z")
    new = bundle("x", "master", "1.0", 2, "2026-10-02T00:00:00Z", reason="push")
    assert diff_builds(new, old, None, None)["classification"] == "linuxserver"


def test_base_change() -> None:
    old = bundle("x", "master", "1.0", 1, "2026-10-01T00:00:00Z", base_digest="1" * 64)
    new = bundle("x", "master", "1.0", 2, "2026-10-02T00:00:00Z", base_digest="2" * 64, reason="rebuild")
    diff = diff_builds(new, old, {"amd64": NEW}, {"amd64": OLD})
    assert diff["classification"] == "base"
    assert diff["base"]["changed"] and diff["base"]["from"]["digest"] == "sha256:" + "1" * 64


def test_packages_only_and_none() -> None:
    old = bundle("x", "master", "1.0", 1, "2026-10-01T00:00:00Z")
    new = bundle("x", "master", "1.0", 2, "2026-10-02T00:00:00Z", reason="packages")
    assert diff_builds(new, old, {"amd64": NEW}, {"amd64": OLD})["classification"] == "packages"
    assert diff_builds(new, old, {"amd64": OLD}, {"amd64": OLD})["classification"] == "none"
    assert diff_builds(new, None, {"amd64": OLD}, None)["classification"] == "initial"


def test_mixed() -> None:
    old = bundle("x", "master", "1.0", 1, "2026-10-01T00:00:00Z", base_digest="1" * 64)
    new = bundle("x", "master", "1.1", 2, "2026-10-02T00:00:00Z", base_digest="2" * 64)
    diff = diff_builds(new, old, None, None)
    assert diff["classification"] == "mixed"
    assert diff["reasons"] == ["upstream version changed", "base image digest changed"]


def test_classify_table() -> None:
    kw = {"initial": False, "upstream_changed": False, "dockerfile_changed": False, "base_changed": False}
    assert classify(**kw, packages_changed=False, reason="rebuild")[0] == "none"
    assert classify(**kw, packages_changed=True, reason="rebuild")[0] == "packages"
    assert classify(**{**kw, "upstream_changed": True}, packages_changed=True, reason="upstream")[0] == "upstream"
    assert classify(**{**kw, "dockerfile_changed": True}, packages_changed=True, reason="push")[0] == "linuxserver"
    assert (
        classify(**{**kw, "upstream_changed": True, "dockerfile_changed": True}, packages_changed=False, reason="push")[
            0
        ]
        == "mixed"
    )


def test_package_diff_by_ecosystem() -> None:
    old = normalise(syft_document([("curl", "8.9.0-r0", "apk"), ("gone", "1", "apk"), ("app", "2.0", "python")]))
    new = normalise(syft_document([("curl", "8.9.1-r0", "apk"), ("fresh", "1", "apk"), ("app", "1.9", "python")]))
    diff = package_diff(old, new)
    assert set(diff) == {"apk", "python"}
    assert [p["name"] for p in diff["apk"]["added"]] == ["fresh"]
    assert [p["name"] for p in diff["apk"]["removed"]] == ["gone"]
    assert [p["name"] for p in diff["apk"]["upgraded"]] == ["curl"]
    assert diff["python"]["downgraded"] == [{"name": "app", "from": "2.0", "to": "1.9", "purl": "pkg:python/app@1.9"}]


def test_normalise_dedupes_and_sorts_and_reads_both_license_shapes() -> None:
    doc = syft_document([("b", "1", "apk"), ("a", "1", "apk"), ("a", "1", "apk"), ("z", "1", "npm")])
    rows = normalise(doc)
    assert [(r["type"], r["name"]) for r in rows] == [("apk", "a"), ("apk", "b"), ("npm", "z")]
    assert rows[0]["licenses"] == ["MIT"] and rows[2]["licenses"] == ["GPL-3.0"]


def test_version_compare() -> None:
    assert compare_versions("1.9", "1.10") == 1
    assert compare_versions("3.22.1", "3.22.1-r0") == 1
    assert compare_versions("1.0.1", "1.0") == -1
    assert compare_versions("2.0.0b1", "2.0.0") == -1  # extra tokens sort after; no pre-release semantics
    assert compare_versions("8.9.1-r0", "8.9.1-r0") == 0
    assert version_key("1.2a") == [(1, 1), (1, 2), (0, "a")]


def test_slug() -> None:
    assert slug("libstdc++") == "libstdc++"
    assert slug("@scope/pkg") == "scope_pkg"
    assert slug("Microsoft.NETCore.App") == "Microsoft.NETCore.App"


def test_dockerfile_diff_ends_with_newline_and_is_empty_when_same() -> None:
    assert dockerfile_diff("a\n", "a\n", "Dockerfile") == ""
    assert dockerfile_diff(None, "a\n", "Dockerfile") == ""
    assert dockerfile_diff("a", "b", "Dockerfile").endswith("\n")


def test_diff_does_not_mutate_inputs() -> None:
    old, new = copy.deepcopy(SONARR_LS1), copy.deepcopy(SONARR_LS2)
    diff_builds(new, old, {"amd64": NEW}, {"amd64": OLD})
    assert old == SONARR_LS1 and new == SONARR_LS2
