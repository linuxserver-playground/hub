"""Every generator against sonarr, swag and the constructed multi-arch image."""

import io
import json
import re
import zipfile

import yaml

from lsio_hub.generate import (
    GENERATORS,
    OUTPUT_DIRS,
    arcane,
    casaos,
    cosmos,
    docs,
    kubernetes,
    mods,
    portainer,
    proxy,
    quadlet,
    runtipi,
    umbrel,
    unraid,
)
from lsio_hub.generate.common import GenerateContext, ImageInput, screenshot_url

from .conftest import FIXTURES


def _image(gen: GenerateContext, name: str) -> ImageInput:
    return next(i for i in gen.images if i.name == name)


def test_every_generator_has_an_output_dir() -> None:
    assert set(GENERATORS) == set(OUTPUT_DIRS)
    assert OUTPUT_DIRS["unraid"] == "stores/unraid" and OUTPUT_DIRS["builds"] == "builds"


def test_docs_pages_are_builders_docs_template(gen: GenerateContext) -> None:
    files = docs.generate(gen)
    page = files["images/docker-sonarr.md"]
    assert isinstance(page, str)
    assert page.startswith("---\ntitle: sonarr\ntags:\n    - Media Management\n")
    assert "# [linuxserver-playground/sonarr](https://github.com/linuxserver-playground/docker-sonarr)" in page
    assert "??? tip" in page or "!!! " in page or "## Parameters" in page
    index = files["images-by-category.md"]
    assert isinstance(index, str)
    assert "## Media Management\n\n- [Sonarr](images/docker-sonarr.md): Sonarr (formerly NZBdrone)" in index
    assert index.index("## Databases") < index.index("## Media Management")


def test_unraid_matches_the_legacy_sample(gen: GenerateContext) -> None:
    ours = unraid.render(_image(gen, "sonarr"))
    sample = (FIXTURES / "unraid-sonarr.xml").read_text()
    # The intended differences: the organisation and registry, the source comment, the template URL (the
    # unraid-store repository), the icon, which is docs.logo now, and the ci screenshot, which is new.
    ours = re.sub(r"    <Screenshot>[^<]*</Screenshot>\n", "", ours)
    for old, new in (
        ("linuxserver-playground", "linuxserver"),
        ("ghcr.io/linuxserver/sonarr", "lscr.io/linuxserver/sonarr"),
        ("linuxserver/unraid-store/main/", "linuxserver/templates/main/unraid/"),
        ("/blob/master/image.yml", "/blob/master/readme-vars.yml"),
        ("sonarr-banner.png", "sonarr-logo.png"),
    ):
        ours = ours.replace(old, new)
    assert ours == sample


def test_unraid_fields_for_the_constructed_image(gen: GenerateContext) -> None:
    xml = unraid.render(_image(gen, "multidb"))
    assert "<ExtraParams>--cap-add=NET_ADMIN --shm-size=1gb</ExtraParams>" in xml
    assert "<WebUI>https://[IP]:[PORT:8080]/login</WebUI>" in xml
    requires = xml[xml.index("<Requires>") : xml.index("</Requires>")]
    assert "A MariaDB container reachable as DB_HOST." in requires
    assert "This container requires an external application" in requires
    assert '<Config Name="Log level" Target="LOG_LEVEL" Default="debug|info|warn"' in xml
    assert 'Target="DB_PASS" Default="changeme" Description="Database password" Type="Variable"' in xml
    assert 'Target="DB_PASS"' in xml and xml[xml.index('Target="DB_PASS"') :].split("/>")[0].endswith('Mask="true"')
    assert 'Name="Path: /lib/modules" Target="/lib/modules" Default="/lib/modules" Mode="ro"' in xml
    assert 'Mode="udp"' in xml and "<Tag>nightly</Tag>" not in xml and "<Overview>Stable branch</Overview>" in xml
    assert '<Config Name="/dev/dri" Default="/dev/dri"' in xml
    files = unraid.generate(gen)
    assert set(files) == {"sonarr.xml", "swag.xml", "multidb.xml", "ignore.list"} and files["ignore.list"] == ""


def test_unraid_deprecated_and_ignored(gen: GenerateContext) -> None:
    swag = _image(gen, "swag")
    swag.manifest["deprecation"] = {"status": True}
    swag.ctx["deprecation"]["status"] = True
    _image(gen, "multidb").manifest.setdefault("publish", {}).setdefault("stores", {})["unraid"] = False
    files = unraid.generate(gen)
    assert "deprecated/swag.xml" in files and "<Deprecated>true</Deprecated>" in str(files["deprecated/swag.xml"])
    assert files["ignore.list"] == "multidb\n" and "multidb.xml" not in files


def test_base_images_and_tools_are_left_out_of_stores_and_install_artefacts(gen: GenerateContext) -> None:
    _image(gen, "swag").manifest["kind"] = "tool"
    _image(gen, "multidb").manifest["kind"] = "base"
    for generator in (portainer, casaos, umbrel, runtipi, cosmos, arcane):
        assert not any("swag" in path or "multidb" in path for path in generator.generate(gen)), generator
    for generator in (unraid, kubernetes, quadlet, proxy):
        paths = [p for p in generator.generate(gen) if p not in ("README.md", "ignore.list")]
        assert paths and all(p.startswith("sonarr") for p in paths), (generator, paths)


def test_proxy_matches_live_samples(gen: GenerateContext) -> None:
    sonarr = _image(gen, "sonarr")
    live = (FIXTURES / "proxy" / "sonarr.subdomain.conf.sample").read_text()
    ours = proxy.subdomain(sonarr)
    assert ours.splitlines()[1:] == live.splitlines()[1:]
    assert ours.startswith("## Version 2026/10/20\n")
    live_folder = (FIXTURES / "proxy" / "sonarr.subfolder.conf.sample").read_text()
    ours_folder = proxy.subfolder(sonarr)
    assert ours_folder is not None
    # The live subfolder sample predates the Tinyauth includes and has no base URL note; everything else matches.
    stripped = [line for line in ours_folder.splitlines()[1:] if "inyauth" not in line and "URL Base" not in line]
    assert [line for line in stripped if line] == [line for line in live_folder.splitlines()[1:] if line]


def test_proxy_websocket_extra_locations_and_no_subfolder(gen: GenerateContext) -> None:
    files = proxy.generate(gen)
    assert set(files) == {
        "README.md",
        "sonarr.subdomain.conf.sample",
        "sonarr.subfolder.conf.sample",
        "multidb.subdomain.conf.sample",
    }
    conf = str(files["multidb.subdomain.conf.sample"])
    assert "# This app serves https itself; the upstream scheme is https." in conf
    assert "set $upstream_proto https;" in conf
    assert 'proxy_set_header Connection "upgrade";' in conf
    assert "location ~ (/multidb)?/api {" in conf and "location ~ (/multidb)?/ws {" in conf
    metrics = conf[conf.index("location /metrics {") :]
    assert "set $upstream_port 9090;" in metrics and "allow 10.0.0.0/8;" in metrics and "auth_basic" not in metrics
    assert conf.rstrip().endswith("}")


def test_portainer_v3(gen: GenerateContext) -> None:
    data = json.loads(str(portainer.generate(gen)["templates.json"]))
    assert data["version"] == "3" and [t["name"] for t in data["templates"]] == ["multidb", "sonarr", "swag"]
    multidb = data["templates"][0]
    assert multidb["type"] == 1 and multidb["platform"] == "linux" and multidb["restart_policy"] == "unless-stopped"
    assert multidb["ports"] == ["8080:8080/tcp"] and multidb["image"] == "ghcr.io/linuxserver-playground/multidb:latest"
    assert multidb["volumes"][0] == {"container": "/config", "bind": "/path/to/multidb/config"}
    assert multidb["volumes"][2]["readonly"] is True
    log_level = next(e for e in multidb["env"] if e["name"] == "LOG_LEVEL")
    assert log_level["label"] == "Log level" and log_level["select"][1] == {
        "text": "info",
        "value": "info",
        "default": True,
    }
    assert multidb["env"][0] == {
        "name": "PUID",
        "label": "PUID",
        "default": "1000",
        "description": "for UserID - see below for explanation",
    }
    assert (
        multidb["categories"] == ["Media Servers", "Databases"] and multidb["logo"] == "https://example.org/multidb.png"
    )


def test_casaos_compose_and_zip(gen: GenerateContext) -> None:
    files = casaos.generate(gen)
    compose = yaml.safe_load(str(files["Apps/sonarr/docker-compose.yml"]))
    meta = compose["x-casaos"]
    assert meta["main"] == "sonarr" and meta["author"] == "LinuxServer.io" and meta["port_map"] == "8989"
    assert (
        meta["scheme"] == "http"
        and meta["category"] == "Media Management"
        and meta["architectures"] == ["amd64", "arm64"]
    )
    assert meta["tagline"]["en_us"].startswith("Sonarr (formerly NZBdrone) is a PVR")
    service = compose["services"]["sonarr"]
    assert service["volumes"][0] == "/DATA/AppData/sonarr/config:/config" and service["ports"] == ["8989:8989"]
    assert service["x-casaos"]["envs"][0]["container"] == "PUID"
    multidb = yaml.safe_load(str(files["Apps/multidb/docker-compose.yml"]))["services"]["multidb"]
    assert multidb["cap_add"] == ["NET_ADMIN"] and "devices" not in multidb
    archive = zipfile.ZipFile(io.BytesIO(files["linuxserver.zip"]))  # type: ignore[arg-type]
    assert sorted(archive.namelist()) == [
        "Apps/multidb/docker-compose.yml",
        "Apps/sonarr/docker-compose.yml",
        "Apps/swag/docker-compose.yml",
    ]
    assert casaos.generate(gen)["linuxserver.zip"] == files["linuxserver.zip"]  # deterministic


def test_umbrel(gen: GenerateContext) -> None:
    files = umbrel.generate(gen)
    assert yaml.safe_load(str(files["umbrel-app-store.yml"])) == {"id": "lsio", "name": "LinuxServer.io"}
    app = yaml.safe_load(str(files["lsio-sonarr/umbrel-app.yml"]))
    assert app["manifestVersion"] == 1 and app["id"] == "lsio-sonarr" and app["port"] == 8989
    assert app["icon"].startswith("https://") and {"lsio-swag/umbrel-app.yml", "lsio-swag/docker-compose.yml"} <= set(
        files
    )
    assert app["version"] == "4.0.20.3014" and app["category"] == "media" and app["developer"] == "LinuxServer.io"
    compose = yaml.safe_load(str(files["lsio-sonarr/docker-compose.yml"]))
    assert compose["services"]["app_proxy"]["environment"] == {"APP_HOST": "lsio-sonarr_server_1", "APP_PORT": 8989}
    server = compose["services"]["server"]
    assert server["volumes"][0] == "${APP_DATA_DIR}/data/config:/config" and server["environment"]["TZ"] == "${TZ}"
    assert str(files["lsio-sonarr/exports.sh"]).startswith('export APP_SONARR_PORT="8989"\n')
    multidb = yaml.safe_load(str(files["lsio-multidb/umbrel-app.yml"]))
    assert multidb["path"] == "/login" and multidb["version"] == "1.0.0"


def test_stores_with_a_screenshot_field_take_the_ci_screenshot(gen: GenerateContext) -> None:
    sonarr = _image(gen, "sonarr")
    assert sonarr.screenshot is not None and sonarr.screenshot.startswith(
        "https://example.github.io/hub/builds/sonarr/"
    )
    assert sonarr.screenshot.endswith("/amd64/screenshot.png")
    assert yaml.safe_load(str(umbrel.generate(gen)["lsio-sonarr/umbrel-app.yml"]))["gallery"] == [sonarr.screenshot]
    meta = yaml.safe_load(str(casaos.generate(gen)["Apps/sonarr/docker-compose.yml"]))["x-casaos"]
    assert meta["screenshot_link"] == [sonarr.screenshot]
    index = json.loads(str(cosmos.generate(gen)["index.json"]))
    assert index["all"][0]["screenshots"] == [sonarr.screenshot]
    assert f"<Screenshot>{sonarr.screenshot}</Screenshot>" in unraid.render(sonarr)
    # A failed capture is never linked: the store would show a timeout or an error page.
    tag = sonarr.record.latest_build()["version"]["tag"]  # type: ignore[index]
    for report in sonarr.record.tests[tag].values():
        for case in report["tests"]:
            if case["name"] == "Take screenshot":
                case["status"] = "FAIL"
    assert screenshot_url(sonarr.record, gen.site) is None


def test_runtipi(gen: GenerateContext) -> None:
    files = runtipi.generate(gen)
    config = json.loads(str(files["apps/multidb/config.json"]))
    assert (
        config["id"] == "multidb"
        and config["port"] == 8080
        and config["tipi_version"] == 1
        and config["version"] == "1.0.0"
    )
    assert config["supported_architectures"] == ["amd64", "arm64"] and config["available"] and config["exposable"]
    assert config["categories"] == ["media", "data"] and config["author"] == "linuxserver.io"
    fields = {f["env_variable"]: f for f in config["form_fields"]}
    assert fields["MULTIDB_DB_PASS"]["type"] == "password" and fields["MULTIDB_DB_PASS"]["required"]
    assert fields["MULTIDB_LOG_LEVEL"]["options"] == [{"label": o, "value": o} for o in ("debug", "info", "warn")]
    assert not fields["MULTIDB_FEATURE_FLAG"]["required"]
    assert "$schema" not in config  # the store ships no schema file
    compose = yaml.safe_load(str(files["apps/multidb/docker-compose.yml"]))
    # Dynamic compose, schema 2: Runtipi adds the ${APP_PORT} mapping, the Traefik labels and the network itself.
    assert compose["x-runtipi"] == {"schema_version": 2}
    service = compose["services"]["multidb"]
    assert service["x-runtipi"] == {"is_main": True, "internal_port": 8080}
    assert service["environment"]["DB_HOST"] == "${MULTIDB_DB_HOST}"
    assert "ports" not in service and "labels" not in service and "networks" not in compose
    assert str(files["apps/multidb/metadata/description.md"]).startswith(
        "# MultiDB\n\n![MultiDB](https://example.org/multidb.png)"
    )


def test_cosmos(gen: GenerateContext) -> None:
    files = cosmos.generate(gen)
    index = json.loads(str(files["index.json"]))
    assert index["source"] == "https://example.github.io/hub/stores/cosmos/index.json" and index["showcase"] == []
    assert [a["id"] for a in index["all"]] == ["sonarr", "swag"]  # multidb has cosmos: false
    sonarr = index["all"][0]
    assert sonarr["compose"].endswith("/stores/cosmos/servapps/sonarr/cosmos-compose.json")
    assert set(sonarr) == {
        "name",
        "longDescription",
        "description",
        "tags",
        "repository",
        "image",
        "supported_architectures",
        "id",
        "screenshots",
        "logo",
        "icon",
        "artefacts",
        "compose",
    }
    compose = json.loads(str(files["servapps/swag/cosmos-compose.json"]))
    service = compose["services"]["{ServiceName}"]
    assert compose["minVersion"] == "0.8.0" and service["routes"][0]["target"] == "http://{ServiceName}:443"
    assert "URL={Context.URL}" in service["environment"] and service["cap_add"] == ["NET_ADMIN"]
    assert compose["cosmos-installer"]["form"][0]["name"] == "URL"
    assert service["volumes"] == [{"source": "{ServiceName}-config", "target": "/config", "type": "volume"}]


def test_kubernetes(gen: GenerateContext) -> None:
    files = kubernetes.generate(gen)
    assert set(files) == {"sonarr.yaml", "swag.yaml", "multidb.yaml"}
    docs_ = list(yaml.safe_load_all(str(files["multidb.yaml"])))
    kinds = [d["kind"] for d in docs_]
    assert kinds == ["ConfigMap", "PersistentVolumeClaim", "PersistentVolumeClaim", "StatefulSet", "Service"]
    sts = docs_[3]
    container = sts["spec"]["template"]["spec"]["containers"][0]
    assert container["securityContext"] == {"capabilities": {"add": ["NET_ADMIN"]}}
    assert [m["mountPath"] for m in container["volumeMounts"]] == ["/config", "/media"]
    assert docs_[0]["data"]["DB_HOST"] == "mariadb" and "FEATURE_FLAG" not in docs_[0]["data"]
    header = str(files["multidb.yaml"]).split("---")[0]
    assert "# Security notes:" in header and "device /dev/dri" in header and "privileged" in header
    sonarr = list(yaml.safe_load_all(str(files["sonarr.yaml"])))
    assert [d["kind"] for d in sonarr] == ["ConfigMap", "PersistentVolumeClaim", "Deployment", "Service"]
    assert sonarr[2]["spec"]["strategy"] == {"type": "Recreate"}


def test_quadlet(gen: GenerateContext) -> None:
    files = quadlet.generate(gen)
    unit = str(files["multidb.container"])
    assert "[Container]\nImage=ghcr.io/linuxserver-playground/multidb:latest\nContainerName=multidb\n" in unit
    assert "AddCapability=NET_ADMIN\n" in unit and "# PodmanArgs=--security-opt seccomp=unconfined" in unit
    assert "Volume=/path/to/multidb/config:/config:Z\n" in unit and "# Volume=/lib/modules:/lib/modules:ro" in unit
    assert "PublishPort=8080:8080\n# PublishPort=1900:1900/udp" in unit
    assert "ShmSize=1gb\n# Sysctl=net.ipv4.ip_forward=1" in unit and "# AddDevice=/dev/dri:/dev/dri" in unit
    assert unit.endswith("[Install]\nWantedBy=default.target\n")
    swag = str(files["swag.container"])
    assert "Environment=URL=example.com\n" in swag and "AddCapability=NET_ADMIN" in swag


def test_mod_list_legacy_shape(gen: GenerateContext) -> None:
    text = str(mods.generate(gen)["mod-list.yml"])
    data = yaml.safe_load(text)
    assert text.startswith("# Generated by the hub")
    assert data["mods"]["sonarr"] == {
        "mod_count": 1,
        "container_mods": [
            {"striptracks": "https://github.com/linuxserver-playground/docker-mods/tree/radarr-striptracks"}
        ],
    }
    assert [k for item in data["mods"]["vscodium-web"]["container_mods"] for k in item] == ["docker", "python3-poetry"]
    assert "nginx" not in data["mods"] and "auto-reload" not in text  # deprecated mods are left out
    assert re.search(r"universal-git\n", text)


def _text(files: dict[str, str | bytes], path: str) -> str:
    value = files[path]
    assert isinstance(value, str), path
    return value


def test_arcane_registry_matches_arcanes_schema(gen: GenerateContext) -> None:
    import hashlib

    import jsonschema

    files = arcane.generate(gen)
    registry = json.loads(_text(files, "registry.json"))
    schema = json.loads((FIXTURES / "arcane-registry.schema.json").read_text())
    jsonschema.Draft7Validator(schema, format_checker=jsonschema.FormatChecker()).validate(registry)
    sonarr = next(t for t in registry["templates"] if t["id"] == "sonarr")
    assert sonarr["compose_url"] == "https://example.github.io/hub/stores/arcane/sonarr/compose.yaml"
    assert sonarr["env_url"].endswith("/stores/arcane/sonarr/env.example")
    compose, env = _text(files, "sonarr/compose.yaml"), _text(files, "sonarr/env.example")
    assert sonarr["content_hash"] == hashlib.sha256((compose + env).encode()).hexdigest()
    assert "linuxserver" in sonarr["tags"]


def test_arcane_compose_takes_its_values_from_env(gen: GenerateContext) -> None:
    files = arcane.generate(gen)
    compose = _text(files, "sonarr/compose.yaml")
    service = yaml.safe_load(compose)["services"]["sonarr"]
    env = _text(files, "sonarr/env.example")
    assert service["environment"]["PUID"] == "${PUID:-1000}" and "PUID=1000" in env
    assert service["volumes"] == ["${CONFIG_PATH:-./config}:/config"]  # optional media folders stay out
    assert service["ports"] == ["${PORT_8989:-8989}:8989"] and "PORT_8989=8989" in env
    assert service["restart"] == "unless-stopped"
    # Every ${VAR} the compose file uses has a line in env.example.
    for var in set(re.findall(r"\$\{([A-Z0-9_]+)", compose)):
        assert re.search(rf"^{var}=", env, re.MULTILINE), var
