# Test fixtures

- `manifests/sonarr.master.yml`, `manifests/sonarr.develop.yml`, `manifests/swag.master.yml`: `image.yml` fetched on
  2026-10-24 from the live `linuxserver-playground` repositories.
- `manifests/multidb.master.yml`: constructed; exercises an external database, devices, capabilities, security
  options, custom flags, selectable variables, a StatefulSet, websocket proxying and a failed arm64 build.
- `unraid-sonarr.xml`: the legacy generator's output from linuxserver/templates, the reference for the Unraid port.
- `proxy/*.sample`: the live linuxserver/reverse-proxy-confs samples, the reference for the proxy generator.
- `live-v1-sonarr.json`: one image from `https://api.linuxserver.io/api/v1/images?include_config=true`, for the
  v1 key order check.
- `mod-list.yml`: linuxserver/docker-mods mod-list.yml as of 2026-10-24, the legacy mods fallback.

Build bundles, syft documents, test reports and report tarballs are constructed in `conftest.py`.
