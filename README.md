# LinuxServer hub

The data nexus of the LinuxServer v2 playground. Every image release attaches a build bundle to its GitHub
Release ([CONVENTIONS.md §6](https://github.com/linuxserver-playground/builder/blob/main/CONVENTIONS.md));
the hub ingests those bundles and every live branch's `image.yml`, keeps the data in git, serves a static API
on GitHub Pages and generates every downstream artefact: docs pages, store templates, SWAG proxy confs,
Kubernetes manifests, Podman quadlets, the mods index and the CI build report pages. It is an evolution of
[static-api](https://github.com/linuxserver/static-api) and keeps its architecture: pydantic models are the
schema, a FastAPI app's routes are rendered to files, data is committed as readable JSON, the OpenAPI spec
and docs page are generated, and the v1 endpoints keep their shape.

```bash
python3.13 -m venv .venv && . .venv/bin/activate
pip install -e '.[dev]'                                  # installs lsio-builder from linuxserver-playground/builder
GITHUB_TOKEN=$(gh auth token) python -m lsio_hub.ingest --reconcile   # data/: manifests, every release's bundle, base layers
GITHUB_TOKEN=$(gh auth token) python -m lsio_hub.observe              # data/observed.json: stars, archived, GHCR tags
GITHUB_TOKEN=$(gh auth token) python -m lsio_hub.mods                 # data/mods.json
python -m lsio_hub.build                                 # dist/: the API, openapi.json, the docs page
python -m lsio_hub.generate [--offline]                  # out/: stores/<platform>/ and builds/
python -m lsio_hub.serve                                 # the same app, live, on http://localhost:8000/
ruff check . && ruff format --check . && mypy && pytest
```

For local work against a checkout of the builder: `pip install -e ../builder` before `pip install -e '.[dev]'`.

## How it works

```
GitHub org (GraphQL, REST) ──┐                     ┌─ dist/api/v1/…           the API (JSON, YAML, Atom)
image.yml per live branch ───┼─ ingest ─> data/ ───┼─ dist/openapi.json, index.html
Release assets (bundles) ────┤  observe   (git)    ├─ out/stores/<platform>/  docs, unraid, portainer, casaos,
GHCR tag lists ──────────────┤  mods               │                          umbrel, runtipi, cosmos, proxy,
docker-mods mod.yml ─────────┘                     │                          kubernetes, quadlet, mods
                                                   └─ out/builds/<image>/<tag>/  CI report pages
```

`deploy.yml` runs hourly (reconcile, observe, mods), on `repository_dispatch` type `image-released`
(`client_payload: {repository, tag}`, sent by the control plane) and on every push to `main`. It commits
`data/` when it changed, builds `dist/`, generates `out/`, merges `out/` onto the site root and deploys to
Pages, so one site serves `/api/v1/…`, `/stores/…` and `/builds/…`. Reads use `GITHUB_TOKEN` only.

| Module | |
| --- | --- |
| `lsio_hub/models.py` | Every response shape. The v1 models are the original API's, field for field. |
| `lsio_hub/store.py` | The `data/` layout: load, save, rotation. |
| `lsio_hub/ingest.py` | Reconcile (every repo, every release) or one release; validates with the builder contracts. |
| `lsio_hub/diff.py`, `packages.py` | The build diff engine and the syft normaliser. |
| `lsio_hub/layers.py` | Layer attribution: `from_base` from the base image's registry manifest, `dockerfile_lines` from `created_by`. |
| `lsio_hub/observe.py`, `mods.py` | The observed poller (stars, archived, GHCR tags; grype is a stub) and the mods index. |
| `lsio_hub/transform.py` | Manifest plus builds to an API image (`builder.manifest.build_context`, `builder.snippets`). |
| `lsio_hub/responses.py`, `app.py`, `build.py` | Endpoint content, the FastAPI routes, the static build. |
| `lsio_hub/generate/` | One module per generator, each a function of `data/`. |

## Data layout

Raw inputs are kept, not finished responses, so a change in derivation needs no refetch and the data commit
is a readable diff. Builds are stored compact, as received; everything else indented.

| Path | What |
| --- | --- |
| `data/images/<name>/manifest.<branch>.json` | `image.yml` of each live branch. Live branches: the default branch, plus every tag in its `release.tags` for which a branch of that name has an `image.yml` publishing that tag. |
| `data/images/<name>/builds/<tag>.json` | `build.json` of a live release, validated against `bundle.schema.json`. |
| `data/images/<name>/builds/<tag>.diff.json` | The diff against the previous build of the same branch. |
| `data/images/<name>/builds/<tag>.layers.<arch>.json` | `layers.<arch>.json` from the Release. |
| `data/images/<name>/builds/<tag>.test.<arch>.json` | `test.<arch>.json` from the Release (validated). |
| `data/images/<name>/packages[.<release tag>].<arch>.json` | Normalised package table (name, version, type, purl, licenses) of the newest build of each branch; no infix for the `latest` branch. |
| `data/images/<name>/latest.json` | branch → tag, created, release URL, asset URLs. |
| `data/images/<name>/history.json` | branch → every release seen, newest first, including rotated-out builds. |
| `data/bases/<algorithm>-<hex>.json` | The layer digests per architecture of a base image, keyed by the index digest builds record as `base.digest`; read from GHCR with an anonymous pull token, once per digest, by the ingest. |
| `data/observed.json` | stars, archived flag, GHCR tag list per image; written by the poller only. |
| `data/mods.json` | The mods index. |
| `data/status.json` | `sources` (manifests, releases, observed, mods: ok, checked_at, fetched_at, error) and `rejected` (releases whose bundle failed validation, with the error; retried every run). |

Rotation keeps the newest 10 builds per branch in git. Older builds stay on their Release; their entry
stays in `history.json` and `latest.json` points at the newest. Heavy assets (`files.<arch>.json.gz`,
tarballs, syft documents) are linked, never committed.

## Endpoints

The static-api endpoints are served at the same paths. Query parameters become files, because a static host
ignores query strings.

| Path | What |
| --- | --- |
| `/health`, `/health.json` | `"Success"` or `"Failed"` (always HTTP 200 from a static host). |
| `/api/v1/images`, `.json`, `.config.json`, `.deprecated.json`, `.config.deprecated.json` | The original list endpoint and its switches. |
| `/api/v1/catalog.json`, `/api/v1/catalog/{name}.json` | Every image, or one, in full (`ImageDetail`). |
| `/api/v1/catalog/{name}/docker-compose.yml` | Compose file from `builder.snippets`. |
| `/api/v1/categories.json`, `/api/v1/stats.json`, `/api/v1/changelog.json`, `.xml` | Fleet views. |
| `/api/v1/status.json` | Source freshness and rejected releases. |
| `/`, `/openapi.json`, `/openapi.yaml` | Docs page and spec. |

Added by the hub:

| Path | What |
| --- | --- |
| `/api/v1/catalog/{name}/builds.json` | Builds in `data/` (newest first) with links, classification, and the release history per branch. `links.files` points at the hub's copy of `files.<arch>.json.gz` (same origin, newest build of each branch) and falls back to the Release asset, which `links.files_release` always carries. |
| `/api/v1/catalog/{name}/builds/{tag}.json` | The bundle record as received. |
| `/api/v1/catalog/{name}/builds/{tag}/report.json` | The build page aggregate: record facts, platforms, result, test summary per arch, diff summary (no package lists), notes and every link. One request per build page. |
| `/api/v1/catalog/{name}/builds/{tag}/tests.json` | The harness's `test.<arch>.json` per arch as received, with a summary (result, passed and failed tests, startup seconds, listening ports, warnings) and the report page URL. Only for builds that have a report. |
| `/api/v1/catalog/{name}/builds/{tag}/diff.json` | Packages per arch by ecosystem, config, base, size and Dockerfile changes, `classification`. |
| `/api/v1/catalog/{name}/builds/{tag}/packages.{arch}.json` | The package table; only for the newest build of each branch (older builds keep `packages.<arch>.json.gz` on the Release). |
| `/api/v1/catalog/{name}/builds/{tag}/layers.{arch}.json` | Layers with digest, size and Dockerfile instruction, plus `from_base` and `dockerfile_lines` (see below). |
| `/api/v1/catalog/{name}/mods.json`, `/api/v1/mods.json` | Mods for one image (its own, then universal), or all. |
| `/api/v1/catalog/{name}/proxy.json` | The SWAG subdomain and subfolder sample texts and the manifest's `proxy` block. |
| `/api/v1/catalog/{name}/kubernetes.yaml`, `/quadlet.container` | Generated documents (only for images where `publish` enables them). |
| `/api/v1/packages.json`, `/api/v1/packages/{package}.json` | Every package name with its file slug; which images ship it, in which versions, per branch and arch. |
| `/api/v1/fleet/bases.json` | Base image references, the images on each, and the digests seen over time. |
| `/api/v1/fleet/staleness.json` | Newest builds whose base was seen newer elsewhere (a later digest in another build, or a later `baseimage-*` release when base images join the fleet). |
| `/api/v1/stores/index.json` | Every store URL with a one-line how-to. |

### Layer attribution

The ci harness emits `from_base` only when the base image is local to the runner, which it usually is not, so
the hub decides it: the ingest reads the base image's manifest from GHCR by the `base.digest` the bundle
records (the index digest), picks the `linux/amd64` and `linux/arm64` manifests and caches their layer digests in
`data/bases/`. A layer is `from_base` when its compressed digest is in that list (`from_base_source: registry`).
When the digests are known for another architecture only, the first N layers are taken, N being the base's
layer count (`count`); when the hub knows nothing, the harness's own flags stand (`harness`) or the field is
absent. `dockerfile_lines` attributes each non-base layer to its `RUN`/`COPY`/`ADD`/`ENV`/`LABEL` instruction by
matching `created_by` (BuildKit's record of the instruction, build args and `/bin/sh -c` stripped) against the
Dockerfile in `build.json`, sequentially from the last layer and the last instruction of the final stage
backwards, so unknown base layers fall off the front; a layer without a confident match has no
`dockerfile_lines`.

### v1 divergences

The v1 list endpoints keep the original field names, order and types; the values now come from the typed
manifest and the build records.

- `version` is the release tag (`<upstream>-ls<N>`) of the newest build of the `latest` branch, as the original
  took GitHub's latest release tag; `latest` before the first build has been ingested. The bare upstream version
  is `ImageDetail.upstream_version`. `version_timestamp` is that build's `created` time (fallback: the repository's
  `pushed_at`, then the refresh time).
- `monthly_pulls` is always absent: the playground has no Scarf or Docker Hub (`exclude_none` drops it; the original
  reported Scarf's count). `Stats` lost `monthly_pulls` and `docker_hub_pulls` and gained `builds`.
- `description` is `summary` from the manifest with newlines joined: Markdown links are kept, where the original
  substituted the bare project name.
- `category` is `docs.categories` joined with commas (no stray spaces). `tags` come from `release.tags`
  (`[{latest, "Stable releases"}]` when absent); `stable` means a `latest` tag is published.
- `architectures` come from `build.platforms` (`amd64` → `x86_64`/`amd64-latest`, `arm64` → `arm64`/`arm64v8-latest`).
- `config` comes from `runtime` through `builder.manifest.normalize_runtime`: required entries first, then
  optional ones, the manifest's defaults applied (`host_path` defaults to `/path/to/<name>/<segment>`). `PUID`,
  `PGID` and `TZ` are listed when `common_env` is on, with the original's descriptions. `privileged: optional`
  reports `true`. `readonly_supported` and `nonroot_supported` are absent when the manifest does not state them.
  `application_setup` points at the README's Application Setup anchor when the manifest has `docs.setup` or a notice.
- `stars` and `archived` come from `data/observed.json` (hourly; GraphQL `stargazerCount` per repository, so the
  playground repositories' real counts, which are 0 so far). `status.json` reports `observed.json`'s `fetched_at`
  under `sources.observed`. `github_url`, `registries` and the docs link point at `linuxserver-playground` and
  `ghcr.io`; `Registries` has `ghcr` and `packages_url` only.
- `ImageDetail` dropped `docker_hub_pulls` and gained `title`, `upstream_version`, `base`, `releases` (one per
  live branch) and `links`.

## Generators

`python -m lsio_hub.generate` writes `out/stores/<platform>/` for every store and `out/builds/` for the
report pages; `--only a,b` limits the run and `--offline` skips Release downloads. Each generator is tested
against sonarr, swag and a constructed multi-arch image with an external database (`tests/fixtures/manifests/multidb.master.yml`).
`<hub>` below is the Pages site, `https://linuxserver-playground.github.io/hub`; the same output is pushed to
the `stores` repository for platforms that clone a git repository.

| Generator | Output | Import |
| --- | --- | --- |
| `docs` | `images/docker-<name>.md` (builder's mkdocs docs template), `images-by-category.md` | Copy into the docs repository's `docs/`. |
| `unraid` | `<name>.xml`, `deprecated/<name>.xml` for `deprecation.status`, `ignore.list` for `publish.stores.unraid: false` | Unraid reads the `unraid/` folder of the stores repository (`<TemplateURL>` points there). Ported field for field from the legacy `unraid.xml.j2`; the icon is `docs.logo`, the WebUI comes from `test.web`, `publish.unraid.requirement` fills `<Requires>`. |
| `portainer` | `templates.json` (format version 3, type 1 templates) | Portainer → Settings → App Templates → URL: `<hub>/stores/portainer/templates.json`. |
| `casaos` | `Apps/<name>/docker-compose.yml` with `x-casaos`, `linuxserver.zip` | CasaOS → App Store → More apps → Add source: `<hub>/stores/casaos/linuxserver.zip`. |
| `umbrel` | `umbrel-app-store.yml` (`id: lsio`), `lsio-<name>/umbrel-app.yml`, `docker-compose.yml` (app_proxy, `APP_DATA_DIR`), `exports.sh` | Umbrel → App Store → Community App Stores → the stores repository (`umbrel/`). |
| `runtipi` | `apps/<name>/config.json`, `docker-compose.yml` with `x-runtipi` (schema_version 2), `metadata/description.md` | Runtipi → Settings → App Stores → the stores repository (`runtipi/`). Runtipi wants `metadata/logo.jpg` as a file; the hub does not copy logos into git, so `config.json` carries `logo_url` (`docs.logo`) and the description page embeds it. |
| `cosmos` | `index.json` (`source`, `showcase`, `all`), `servapps/<name>/description.json`, `cosmos-compose.json` | Cosmos → Market → Sources → `<hub>/stores/cosmos/index.json`. Matches the TinyActive community source (fetched 2026-10-24). |
| `proxy` | `<name>.subdomain.conf.sample`, `<name>.subfolder.conf.sample`, `README.md` | The proxy-confs repository; SWAG pulls it into `/config/nginx/proxy-confs/`. Reproduces the live sonarr samples: auth includes as comments, `api_locations` without auth, websocket upgrade headers when `websocket`, `extra_locations`, `notes` as header comments. |
| `kubernetes` | `<name>.yaml`: ConfigMap, PVC per `publish.kubernetes.persistence` (default: required volumes), Deployment or StatefulSet, Service; security notes as comments | `kubectl apply -f <hub>/stores/kubernetes/<name>.yaml` after editing storage sizes. |
| `quadlet` | `<name>.container` | Copy to `~/.config/containers/systemd/`, `systemctl --user daemon-reload`. |
| `mods` | `mod-list.yml` in the legacy shape | `<hub>/stores/mods/mod-list.yml`; the structured index is `/api/v1/mods.json`. |
| `builds` | see below | `<hub>/builds/<image>/<tag>/` |

The mods index reads `mod.yml` from every branch of `linuxserver-playground/docker-mods`; those entries are
`source: playground` with the image `ghcr.io/linuxserver-playground/mods:<target>-<name>`. **That repository
does not exist yet**, so today the index comes from the legacy `linuxserver/docker-mods` `mod-list.yml`, read
(never written) and converted: the branch is `<target>-<name>`, images that list a mod go into `applies_to`,
each entry is `source: legacy`, and the image reference stays `ghcr.io/linuxserver/mods:<branch>` because that
is where those mods live; nothing is rewritten to the playground namespace. `data/mods.json` records which
source was used (`source` at the top), and the fallback goes away by itself once the playground repository
has `mod.yml` branches.

### Build report pages

The control plane shows live status only; everything rendered from a Release lives here. For every ingested
build the hub emits `out/builds/<image>/<tag>/index.html` (result per arch, the test table from
`test.<arch>.json`, the runtime probe, links to the run, Release and API, the diff summary, release notes) and
unpacks `test.<arch>.tar.gz` next to it (`<arch>/index.html`, `screenshot.png`, `container.log`,
`browser.log`, `sysinfo.txt`, `package_diff.txt`). `files.<arch>.json.gz` is copied for the newest build of each
branch; older builds link to the Release asset. `out/builds/<image>/index.html` is the build history of the
image. Tarballs are downloaded at generation time, never committed; the workflow caches `out/builds` so a run
only fetches new builds, and `--offline` renders the pages with links to the Release instead. Images are
copied as they are (Pages gzips text).

## Deploying

1. Set Pages to deploy from GitHub Actions. The build takes the site URL and base path from
   `actions/configure-pages`, so links and the spec's `servers` entry follow a custom domain.
2. The data commit (`Update data`) is pushed to `main` by `github-actions[bot]`; branch protection must allow it.
3. The control plane triggers `repository_dispatch` type `image-released` with
   `{"repository": "linuxserver-playground/docker-sonarr", "tag": "4.0.20.3014-ls1"}`; the hourly reconcile
   catches anything missed.

## Notes on the contracts

- `CONVENTIONS.md §3` says a Release's `target_commitish` is the branch name; the shared workflow currently
  writes the commit sha. The hub guesses the branch from the tag prefix and verifies it against `branch` in the
  bundle, rejecting bundles for non-live branches.
- `lsio-builder` pins `jsonschema==4.25.1` and `referencing==0.36.2` exactly, which rules out
  `openapi-spec-validator>=0.8`; the dev dependency is pinned to 0.7.2.
- `lsio-builder` ships no `py.typed`, so `mypy --strict` treats it as untyped (see `pyproject.toml`).
