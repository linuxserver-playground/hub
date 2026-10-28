"""data/ round-trips exactly, rotation removes files, and a missing directory loads as empty."""

import json
from pathlib import Path

from lsio_hub.ingest import rotate
from lsio_hub.store import Store, load_store, packages_filename, save_store

from .conftest import build_store


def _tree(directory: Path) -> dict[str, bytes]:
    return {str(p.relative_to(directory)): p.read_bytes() for p in directory.rglob("*") if p.is_file()}


def test_round_trips_byte_for_byte(tmp_path: Path) -> None:
    save_store(tmp_path, build_store())
    first = _tree(tmp_path)
    assert not save_store(tmp_path, load_store(tmp_path))
    assert _tree(tmp_path) == first


def test_layout(tmp_path: Path) -> None:
    save_store(tmp_path, build_store())
    sonarr = tmp_path / "images" / "sonarr"
    assert (sonarr / "manifest.master.json").is_file() and (sonarr / "manifest.develop.json").is_file()
    assert (sonarr / "builds" / "4.0.20.3014-ls2.json").is_file()
    assert (sonarr / "builds" / "4.0.20.3014-ls2.diff.json").is_file()
    assert (sonarr / "builds" / "4.0.20.3014-ls2.layers.amd64.json").is_file()
    assert (sonarr / "builds" / "4.0.20.3014-ls2.test.arm64.json").is_file()
    assert (sonarr / "builds" / "4.0.20.3014-ls2.vulns.json").is_file()  # the counts of the build's own scan
    assert not (sonarr / "builds" / "4.0.19.2000-ls1.vulns.json").is_file()  # an older release made none
    assert (sonarr / "packages.amd64.json").is_file()
    assert (sonarr / "packages.develop.amd64.json").is_file()
    assert (sonarr / "latest.json").is_file() and (sonarr / "history.json").is_file()
    assert (tmp_path / "observed.json").is_file() and (tmp_path / "mods.json").is_file()
    # Builds are compact; everything else is indented for readable diffs.
    assert b"\n" not in (sonarr / "builds" / "4.0.20.3014-ls2.json").read_bytes().rstrip(b"\n")
    assert (sonarr / "manifest.master.json").read_text().startswith("{\n ")


def test_proot_apps_json_is_only_written_by_its_refresh(tmp_path: Path) -> None:
    """The Deploy saves a store loaded from data/; before the refresh has run once, it must not create the file."""
    store = build_store()
    save_store(tmp_path, store)
    assert (tmp_path / "proot-apps.json").is_file()
    empty = tmp_path / "empty"
    store.proot_apps = {}
    save_store(empty, store)
    assert not (empty / "proot-apps.json").exists()


def test_packages_filename() -> None:
    assert packages_filename("latest", "amd64") == "packages.amd64.json"
    assert packages_filename("develop", "arm64") == "packages.develop.arm64.json"


def test_rotation_drops_old_builds_but_keeps_history(tmp_path: Path) -> None:
    store = build_store()
    sonarr = store.images["sonarr"]
    assert rotate(sonarr, keep=1) == ["4.0.19.2000-ls1"]
    assert sorted(sonarr.builds) == ["4.0.20.3014-ls2", "develop-5.0.1.1234-ls1"]
    assert "4.0.19.2000-ls1" not in sonarr.diffs and "4.0.19.2000-ls1" not in sonarr.tests
    assert [h["tag"] for h in sonarr.history["master"]] == ["4.0.20.3014-ls2", "4.0.19.2000-ls1"]
    save_store(tmp_path, store)
    assert not list((tmp_path / "images" / "sonarr" / "builds").glob("4.0.19.2000-ls1*"))
    # The rotated build keeps the run that built it in history.json, which the site links instead of a page.
    history = json.loads((tmp_path / "images" / "sonarr" / "history.json").read_text())
    assert history["master"][1]["run_url"].endswith("/docker-sonarr/actions/runs/1001")


def test_rotation_records_the_run_of_history_written_before_it_carried_one() -> None:
    store = build_store()
    sonarr = store.images["sonarr"]
    for entries in sonarr.history.values():
        for entry in entries:
            entry.pop("run_url")
    rotate(sonarr, keep=1)
    assert [h["run_url"][-4:] for h in sonarr.history["master"]] == ["1002", "1001"]


def test_five_builds_are_kept_per_branch_as_on_the_repository_pages() -> None:
    from lsio_hub.config import KEEP_BUILDS

    assert KEEP_BUILDS == 5


def test_removed_image_directory_is_deleted(tmp_path: Path) -> None:
    store = build_store()
    save_store(tmp_path, store)
    store.images.pop("swag")
    assert "-images/swag" in save_store(tmp_path, store)
    assert not (tmp_path / "images" / "swag").exists()


def test_missing_data_loads_as_empty(tmp_path: Path) -> None:
    store = load_store(tmp_path)
    assert store.images == {} and store.status == Store().status


def test_record_helpers() -> None:
    sonarr = build_store().images["sonarr"]
    assert sonarr.default_branch == "master"
    assert sonarr.branch_of("develop") == "develop"
    latest = sonarr.latest_build()
    assert latest is not None and latest["version"]["tag"] == "4.0.20.3014-ls2"
    assert [b["version"]["tag"] for b in sonarr.builds_of("master")] == ["4.0.20.3014-ls2", "4.0.19.2000-ls1"]


def test_bases_round_trip_and_prune(tmp_path: Path, store: Store) -> None:
    store.bases["sha256:" + "f" * 64] = {"image": "x", "digest": "sha256:" + "f" * 64, "platforms": {}}
    changed = save_store(tmp_path, store)
    assert f"bases/sha256-{'b' * 64}.json" in changed and not any("f" * 64 in c for c in changed)  # unreferenced
    loaded = load_store(tmp_path)
    assert list(loaded.bases) == ["sha256:" + "b" * 64]
    assert (
        loaded.bases["sha256:" + "b" * 64]["platforms"]["amd64"]["layers"]
        == store.bases["sha256:" + "b" * 64]["platforms"]["amd64"]["layers"]
    )
    for record in loaded.images.values():
        record.builds.clear()
    assert f"-bases/sha256-{'b' * 64}.json" in save_store(tmp_path, loaded)
    assert not (tmp_path / "bases" / f"sha256-{'b' * 64}.json").exists()


def test_status_has_one_file_per_writer(tmp_path: Path) -> None:
    """The release path and the hourly refresh commit concurrently, so each source's status is a file of its own."""
    store = build_store()
    save_store(tmp_path, store)
    status = tmp_path / "status"
    assert sorted(p.name for p in status.iterdir()) == [
        "bases.json",
        "manifests.json",
        "mods.json",
        "observed.json",
        "proot-apps.json",
        "rejected.json",
        "releases.json",
    ]
    assert not (tmp_path / "status.json").exists()
    store.status["sources"]["observed"] = {"ok": False, "checked_at": "x"}
    assert save_store(tmp_path, store) == ["status/observed.json"]
    assert load_store(tmp_path).status == store.status


def test_legacy_status_file_is_read_and_replaced(tmp_path: Path) -> None:
    store = build_store()
    save_store(tmp_path, store)
    legacy = {"sources": store.status["sources"], "rejected": store.status["rejected"]}
    for path in (tmp_path / "status").iterdir():
        path.unlink()
    (tmp_path / "status.json").write_text(json.dumps(legacy))
    loaded = load_store(tmp_path)
    assert loaded.status["sources"] == store.status["sources"] and loaded.status["rejected"] == store.status["rejected"]
    changed = save_store(tmp_path, loaded)
    assert "-status.json" in changed and (tmp_path / "status" / "releases.json").is_file()
