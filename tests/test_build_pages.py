"""The CI report pages under out/builds/."""

import gzip
import io
import tarfile
from pathlib import Path

from lsio_hub.generate import builds, generate_all, write_output
from lsio_hub.generate.common import GenerateContext

from .conftest import asset_bytes, make_report, report_tarball


def test_pages_and_unpacked_reports(gen: GenerateContext) -> None:
    files = builds.generate(gen)
    assert "report.css" in files and "sonarr/index.html" in files
    page = str(files["sonarr/4.0.20.3014-ls2/index.html"])
    assert "<title>sonarr 4.0.20.3014-ls2 · build report</title>" in page
    assert 'class="pill success">amd64: success' in page and "tests passed" in page
    assert "Changes since 4.0.19.2000-ls1" in page and 'class="pill none">upstream' in page
    assert "<td>Take screenshot</td>" in page and "<dt>RSS</dt><dd>114.4 MiB</dd>" in page
    assert 'href="amd64/index.html">HTML report</a>' in page and 'src="amd64/screenshot.png"' in page
    assert 'href="https://github.com/linuxserver-playground/docker-sonarr/actions/runs/1002">workflow run</a>' in page
    assert "https://example.github.io/hub/api/v1/catalog/sonarr/builds/4.0.20.3014-ls2/diff.json" in page
    assert "* Add krb5-libs" in page
    assert files["sonarr/4.0.20.3014-ls2/amd64/index.html"] == b"<html><body><h1>sonarr amd64 report</h1></body></html>"
    assert files["sonarr/4.0.20.3014-ls2/amd64/container.log"] == b"[ls.io-init] done.\n"
    assert (
        "sonarr/4.0.20.3014-ls2/amd64/package_diff.txt" in files and "sonarr/4.0.20.3014-ls2/amd64/sysinfo.txt" in files
    )
    assert not [p for p in files if "escape" in p]


def test_file_trees_only_for_the_newest_build_of_a_branch(gen: GenerateContext) -> None:
    files = builds.generate(gen)
    assert "sonarr/4.0.20.3014-ls2/files.amd64.json.gz" in files
    assert "sonarr/develop-5.0.1.1234-ls1/files.arm64.json.gz" in files
    assert "sonarr/4.0.19.2000-ls1/files.amd64.json.gz" not in files
    old = str(files["sonarr/4.0.19.2000-ls1/index.html"])
    assert "https://assets.test/sonarr/4.0.19.2000-ls1/files.amd64.json.gz" in old and "(release)" in old
    assert gzip.decompress(files["sonarr/4.0.20.3014-ls2/files.amd64.json.gz"]).startswith(b"[")  # type: ignore[arg-type]


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


def test_offline_pages_link_to_the_release(gen: GenerateContext) -> None:
    gen.fetch = lambda url: None
    files = builds.generate(gen)
    page = str(files["sonarr/4.0.20.3014-ls2/index.html"])
    assert "amd64/index.html" not in page and "test.amd64.tar.gz</a>" in page
    assert "sonarr/4.0.20.3014-ls2/amd64/index.html" not in files


def test_existing_output_is_not_downloaded_again(gen: GenerateContext) -> None:
    urls: list[str] = []

    def fetch(url: str) -> bytes | None:
        urls.append(url)
        return asset_bytes(url)

    gen.fetch = fetch
    gen.extra["existing"] = {"sonarr/4.0.20.3014-ls2/amd64/index.html", "sonarr/4.0.20.3014-ls2/files.amd64.json.gz"}
    files = builds.generate(gen)
    assert "https://assets.test/sonarr/4.0.20.3014-ls2/test.amd64.tar.gz" not in urls
    assert "https://assets.test/sonarr/4.0.20.3014-ls2/files.amd64.json.gz" not in urls
    assert "https://assets.test/sonarr/4.0.20.3014-ls2/test.arm64.tar.gz" in urls
    page = str(files["sonarr/4.0.20.3014-ls2/index.html"])
    assert 'href="amd64/index.html">HTML report</a>' in page and 'href="files.amd64.json.gz"' in page


def test_unpack_strips_one_root_and_rejects_escapes() -> None:
    report = make_report("x", "1-ls1", "amd64")
    out = builds.unpack(report_tarball("x", "amd64"), report)
    assert set(out) == {"index.html", "container.log", "screenshot.png", "sysinfo.txt", "package_diff.txt"}
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        for name in ("/abs.txt", "../up.txt", "ok/other.bin"):
            info = tarfile.TarInfo(name)
            info.size = 1
            tar.addfile(info, io.BytesIO(b"x"))
    assert builds.unpack(buffer.getvalue(), None) == {"other.bin": b"x"}


def test_write_output_merges_dirs_and_keeps_cached_assets(tmp_path: Path, gen: GenerateContext) -> None:
    outputs = generate_all(gen, {"quadlet", "builds"})
    written = write_output(tmp_path, outputs)
    assert "stores/quadlet/sonarr.container" in written and (tmp_path / "builds" / "sonarr" / "index.html").is_file()
    stale = tmp_path / "stores" / "quadlet" / "gone.container"
    stale.write_text("x")
    cached = tmp_path / "builds" / "sonarr" / "4.0.20.3014-ls2" / "amd64" / "index.html"
    gen.fetch = lambda url: None
    write_output(
        tmp_path, generate_all(gen, {"quadlet", "builds"}), keep={"builds/sonarr/4.0.20.3014-ls2/amd64/index.html"}
    )
    assert not stale.exists() and cached.is_file()


def test_reports_are_fetched_once_and_rotated_builds_dropped(tmp_path: Path, gen: GenerateContext) -> None:
    """A second run downloads nothing and keeps every unpacked file, including a report without an HTML page."""
    from lsio_hub.generate import existing_paths

    urls: list[str] = []

    def fetch(url: str) -> bytes | None:
        urls.append(url)
        if url.endswith("/swag/5.2.0-ls1/test.amd64.tar.gz"):  # a tarball with no report in it
            buffer = io.BytesIO()
            with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
                info = tarfile.TarInfo("report/container.log")
                info.size = 2
                tar.addfile(info, io.BytesIO(b"x\n"))
            return buffer.getvalue()
        return asset_bytes(url)

    def run() -> None:
        gen.fetch = fetch
        gen.extra = {"existing": existing_paths(tmp_path, "builds")}
        outputs = generate_all(gen, {"builds"})
        write_output(tmp_path, outputs, keep={f"builds/{p}" for p in gen.extra["keep"]})

    run()
    first = sorted(p.relative_to(tmp_path) for p in (tmp_path / "builds").rglob("*") if p.is_file())
    assert (tmp_path / "builds/swag/5.2.0-ls1/amd64/fetched.json").read_text() == '["container.log"]\n'
    assert urls
    urls.clear()
    run()
    assert urls == []
    assert sorted(p.relative_to(tmp_path) for p in (tmp_path / "builds").rglob("*") if p.is_file()) == first
    page = (tmp_path / "builds/sonarr/4.0.20.3014-ls2/index.html").read_text()
    assert 'href="amd64/index.html">HTML report</a>' in page and 'href="amd64/container.log"' in page
    assert "fetched.json" not in page

    sonarr = gen.store.images["sonarr"]
    sonarr.builds.pop("4.0.19.2000-ls1")
    run()
    assert not (tmp_path / "builds/sonarr/4.0.19.2000-ls1").exists()
    assert (tmp_path / "builds/sonarr/4.0.20.3014-ls2/amd64/index.html").is_file()
