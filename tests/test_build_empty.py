"""A new organisation (Labs) has been ingested but has no images yet: the hub still publishes an empty API."""

from pathlib import Path

import pytest

from lsio_hub import build
from lsio_hub.store import load_store, save_store


def test_an_ingested_org_without_images_renders_an_empty_api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data = tmp_path / "data"
    store = load_store(data)
    at = "2026-11-02T12:00:00Z"  # a reconcile ran and found no image repositories
    store.status.setdefault("sources", {})["manifests"] = {"ok": True, "checked_at": at, "fetched_at": at}
    save_store(data, store)
    monkeypatch.setattr(build, "DATA_DIR", data)
    monkeypatch.setattr(build, "DIST_DIR", tmp_path / "dist")
    assert build.main() == 0
    assert (tmp_path / "dist" / "api" / "v1" / "images.json").is_file()


def test_a_checkout_without_data_still_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(build, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(build, "DIST_DIR", tmp_path / "dist")
    assert build.main() == 1
