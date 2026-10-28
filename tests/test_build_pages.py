"""The CI report pages under out/builds/: plain pages that link the heavy files on each repository's Pages."""

from pathlib import Path

from lsio_hub.generate import builds, generate_all, write_output
from lsio_hub.generate.common import GenerateContext

PAGES = "https://linuxserver-playground.github.io/docker-sonarr/builds"


def test_pages_link_the_report_files_on_the_repository_pages(gen: GenerateContext) -> None:
    files = builds.generate(gen)
    assert "report.css" in files and "sonarr/index.html" in files
    page = str(files["sonarr/4.0.20.3014-ls2/index.html"])
    assert "<title>sonarr 4.0.20.3014-ls2 · build report</title>" in page
    assert 'class="pill success">amd64: success' in page and "tests passed" in page
    assert "Changes since 4.0.19.2000-ls1" in page and 'class="pill none">upstream' in page
    assert "<td>Take screenshot</td>" in page and "<dt>RSS</dt><dd>114.4 MiB</dd>" in page
    assert "HTML report" not in page and f'src="{PAGES}/4.0.20.3014-ls2/amd64/screenshot.png"' in page
    assert f'href="{PAGES}/4.0.20.3014-ls2/amd64/container.log"' in page
    assert f'href="{PAGES}/4.0.20.3014-ls2/arm64/package_diff.txt"' in page
    assert 'href="https://github.com/linuxserver-playground/docker-sonarr/actions/runs/1002">workflow run</a>' in page
    assert "https://example.github.io/hub/api/v1/catalog/sonarr/builds/4.0.20.3014-ls2/diff.json" in page
    assert 'href="https://assets.test/sonarr/4.0.20.3014-ls2/test.amd64.tar.gz">test.amd64.tar.gz</a>' in page
    assert "* Add krb5-libs" in page
    # Only pages: nothing is copied or unpacked next to them.
    assert {p.rsplit("/", 1)[-1] for p in files} == {"report.css", "index.html"}


def test_every_held_build_links_its_file_trees_on_the_repository_pages(gen: GenerateContext) -> None:
    files = builds.generate(gen)
    for tag in ("4.0.20.3014-ls2", "4.0.19.2000-ls1"):
        assert f'href="{PAGES}/{tag}/files.amd64.json.gz"' in str(files[f"sonarr/{tag}/index.html"])
    assert "assets.test/sonarr/4.0.19.2000-ls1/files" not in str(files["sonarr/4.0.19.2000-ls1/index.html"])


def test_failed_arch_and_disabled_tests(gen: GenerateContext) -> None:
    files = builds.generate(gen)
    page = str(files["multidb/1.0.0-ls1/index.html"])
    assert 'class="pill failure">arm64: failure' in page and "tests failed" in page
    assert 'class="pill FAIL">FAIL' in page and "Dotnet runtime check warned" in page
    swag = str(files["swag/5.2.0-ls1/index.html"])
    assert "tests disabled" in swag


def test_history_page(gen: GenerateContext) -> None:
    page = str(builds.generate(gen)["sonarr/index.html"])
    rows = page.split("<tr>")[2:]
    assert [r.split("<code>")[1].split("</code>")[0] for r in rows] == [
        "develop-5.0.1.1234-ls1",
        "4.0.20.3014-ls2",
        "4.0.19.2000-ls1",
    ]
    assert 'href="4.0.20.3014-ls2/"' in page and "Older releases" not in page


def test_write_output_merges_dirs_and_drops_what_is_gone(tmp_path: Path, gen: GenerateContext) -> None:
    written = write_output(tmp_path, generate_all(gen, {"quadlet", "builds"}))
    assert "stores/quadlet/sonarr.container" in written and (tmp_path / "builds" / "sonarr" / "index.html").is_file()
    stale = tmp_path / "stores" / "quadlet" / "gone.container"
    stale.write_text("x")
    # What older runs unpacked next to the pages goes on the next run.
    unpacked = tmp_path / "builds" / "sonarr" / "4.0.20.3014-ls2" / "amd64" / "container.log"
    unpacked.parent.mkdir(parents=True)
    unpacked.write_text("x")
    gen.store.images["sonarr"].builds.pop("4.0.19.2000-ls1")
    write_output(tmp_path, generate_all(gen, {"quadlet", "builds"}))
    assert not stale.exists() and not unpacked.exists() and not unpacked.parent.exists()
    assert not (tmp_path / "builds/sonarr/4.0.19.2000-ls1").exists()
    assert (tmp_path / "builds/sonarr/4.0.20.3014-ls2/index.html").is_file()
