"""The retired CI report pages under out/builds/: a small redirect per build the hub knows, to the website."""

from pathlib import Path

from lsio_hub.generate import builds, generate_all, write_output
from lsio_hub.generate.common import GenerateContext

SITE = "https://linuxserver-playground.github.io/site/images"


def test_every_known_build_redirects_to_its_page_on_the_website(gen: GenerateContext) -> None:
    sonarr = gen.store.images["sonarr"]
    # A release rotated out of data/ is still in history.json, and the site still renders it (its 404 page).
    sonarr.history["master"].append({"tag": "4.0.18.1000-ls1", "created": "2026-09-01T00:00:00Z"})
    files = builds.generate(gen)
    assert {p.rsplit("/", 1)[-1] for p in files} == {"index.html"}
    tags = {p.split("/")[1] for p in files if p.startswith("sonarr/") and p.count("/") == 2}
    assert tags == {"4.0.20.3014-ls2", "4.0.19.2000-ls1", "develop-5.0.1.1234-ls1", "4.0.18.1000-ls1"}
    page = str(files["sonarr/4.0.20.3014-ls2/index.html"])
    target = f"{SITE}/sonarr/builds/4.0.20.3014-ls2/"
    assert f'<meta http-equiv="refresh" content="0; url={target}">' in page
    assert f'<link rel="canonical" href="{target}">' in page and f'<a href="{target}">sonarr 4.0.20.3014-ls2 on' in page
    assert '<meta name="robots" content="noindex">' in page and "<title>sonarr 4.0.20.3014-ls2</title>" in page
    assert len(page.encode()) < 600
    assert f"url={SITE}/sonarr/builds/4.0.18.1000-ls1/" in str(files["sonarr/4.0.18.1000-ls1/index.html"])
    assert f"url={SITE}/sonarr/#builds" in str(files["sonarr/index.html"])
    assert "multidb/1.0.0-ls1/index.html" in files and "swag/5.2.0-ls1/index.html" in files


def test_a_tag_that_is_not_one_path_segment_gets_no_page(gen: GenerateContext) -> None:
    gen.store.images["sonarr"].history["master"].append({"tag": "../escape", "created": "2026-09-01T00:00:00Z"})
    assert not [p for p in builds.generate(gen) if "escape" in p]


def test_write_output_merges_dirs_and_drops_what_is_gone(tmp_path: Path, gen: GenerateContext) -> None:
    written = write_output(tmp_path, generate_all(gen, {"quadlet", "builds"}))
    assert "stores/quadlet/sonarr.container" in written and (tmp_path / "builds" / "sonarr" / "index.html").is_file()
    stale = tmp_path / "stores" / "quadlet" / "gone.container"
    stale.write_text("x")
    # What older runs wrote next to the pages (the report pages' unpacked files) goes on the next run.
    unpacked = tmp_path / "builds" / "sonarr" / "4.0.20.3014-ls2" / "amd64" / "container.log"
    unpacked.parent.mkdir(parents=True)
    unpacked.write_text("x")
    sonarr = gen.store.images["sonarr"]
    sonarr.builds.pop("4.0.19.2000-ls1")
    sonarr.history["master"] = [h for h in sonarr.history["master"] if h["tag"] != "4.0.19.2000-ls1"]
    write_output(tmp_path, generate_all(gen, {"quadlet", "builds"}))
    assert not stale.exists() and not unpacked.exists() and not unpacked.parent.exists()
    assert not (tmp_path / "builds/sonarr/4.0.19.2000-ls1").exists()
    assert (tmp_path / "builds/sonarr/4.0.20.3014-ls2/index.html").is_file()
