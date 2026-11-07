"""The publish digest: a rebuild that only moved the Deploy's own times is no change; anything else is."""

import json
from pathlib import Path

from lsio_hub.pages_digest import digest

AT = "2026-11-07T12:38:40.496Z"
LATER = "2026-11-07T12:42:52.437Z"


def data(tmp: Path, at: str) -> Path:
    status = tmp / "data" / "status"
    status.mkdir(parents=True, exist_ok=True)
    for source in ("manifests", "releases"):
        (status / f"{source}.json").write_text(json.dumps({"ok": True, "checked_at": at, "fetched_at": at}))
    return tmp / "data"


def site(tmp: Path, at: str, python: str, page: str, stars: int = 5) -> Path:
    root = tmp / "dist"
    (root / "api").mkdir(parents=True, exist_ok=True)
    (root / "api" / "images.json").write_text(json.dumps({"last_updated": python, "stars": stars}))
    (root / "index.html").write_text(f'<time datetime="{at}">{page}</time>')
    (root / "deploy.json").write_text(json.dumps({"run_id": len(at)}))
    return root


def test_only_the_deploys_own_times_moved(tmp_path: Path) -> None:
    first = digest(
        site(tmp_path / "a", AT, "2026-11-07 12:38:40+00:00", "7 Nov 2026, 12:38 UTC"), data(tmp_path / "a", AT)
    )
    second = digest(
        site(tmp_path / "b", LATER, "2026-11-07 12:42:52+00:00", "7 Nov 2026, 12:42 UTC"), data(tmp_path / "b", LATER)
    )
    assert first == second


def test_a_real_change_shows(tmp_path: Path) -> None:
    first = digest(
        site(tmp_path / "a", AT, "2026-11-07 12:38:40+00:00", "7 Nov 2026, 12:38 UTC"), data(tmp_path / "a", AT)
    )
    second = digest(
        site(tmp_path / "b", LATER, "2026-11-07 12:42:52+00:00", "7 Nov 2026, 12:42 UTC", stars=6),
        data(tmp_path / "b", LATER),
    )
    assert first != second
