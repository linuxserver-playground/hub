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
GITHUB_TOKEN=$(gh auth token) python -m lsio_hub.observe              # data/observed.json: stars, archived, GHCR tags; then grype
GITHUB_TOKEN=$(gh auth token) python -m lsio_hub.vulns                # the grype scan alone (GRYPE=/path/to/grype)
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

Two workflows share the work, and each writes only its own files in `data/` (see `lsio_hub/store.py`), so they
run at the same time and their data commits never conflict.

- `deploy.yml` is the release path. It runs on `repository_dispatch` type `image-released` (sent by the control
  plane after every live release; its payload is only a hint), on every push to `main`, on demand, and when
  `refresh.yml` has new data. Every run reconciles the whole organisation (`ingest --reconcile`): every `image.yml`
  and the newest 30 releases of every repository over GraphQL, in about 15 seconds, then the assets of whatever is
  new. GitHub keeps one pending run per concurrency group and drops older ones, so a burst of releases is picked
  up by whichever run comes next and none is lost. It commits `data/` when it changed, builds `dist/`, generates
  `out/`, merges `out/` onto the site root and deploys to Pages, so one site serves `/api/v1/…`, `/stores/…` and
  `/builds/…`. It is a single job: every job is a separate wait for a runner slot when image builds fill them.
- `refresh.yml` runs hourly (its cron, and a dispatch from the control plane): `observe` (stars, archived flags,
  GHCR tags, then the grype scan) and `mods`. It commits what changed and dispatches `deploy.yml`, then pushes the
  Unraid, Umbrel and Runtipi stores to their own repositories (see Generators).

The Arcane template registry is served from Pages: `<hub>/stores/arcane/registry.json`. Reads use `GITHUB_TOKEN` only.

| Module | |
| --- | --- |
| `lsio_hub/models.py` | Every response shape. The v1 models are the original API's, field for field. |
| `lsio_hub/store.py` | The `data/` layout: load, save, rotation. |
| `lsio_hub/ingest.py` | Reconcile (every repo's manifests and every release `data/` lacks; `--deep` lists every release over REST for a backfill) or one release; validates with the builder contracts. |
| `lsio_hub/diff.py`, `packages.py` | The build diff engine and the syft normaliser: `builder.derive`'s, which the build also runs. |
| `lsio_hub/layers.py` | Layer attribution: `from_base` from the base image's registry manifest, `dockerfile_lines` from `created_by`. |
| `lsio_hub/observe.py`, `vulns.py`, `mods.py` | The observed pollers (stars, archived, GHCR tags; grype against the newest build of each branch) and the mods index. |
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
| `data/images/<name>/builds/<tag>.vulns.<arch>.json` | grype's findings against the build's syft SBOM, compact: `{db_date, grype_version, scanned_at, matches: [{package, version, type, id, severity, fix_state, fixed_in, urls, cvss}]}`. From the build's own `record.json`, then rescanned by the vulnerability poller for the newest build of each branch. |
| `data/images/<name>/packages[.<release tag>].<arch>.json` | Normalised package table (name, version, type, purl, licenses) of the newest build of each branch; no infix for the `latest` branch. |
| `data/images/<name>/latest.json` | branch → tag, created, release URL, asset URLs. |
| `data/images/<name>/history.json` | branch → every release seen, newest first, including rotated-out builds. |
| `data/bases/<algorithm>-<hex>.json` | The layer digests per architecture of a base image, keyed by the index digest builds record as `base.digest`; read from GHCR with an anonymous pull token, once per digest, by the ingest. |
| `data/observed.json` | stars, archived flag, GHCR tag list per image; written by the poller only. `vulnerabilities` is the scan ledger: the database date and grype version last used, and per newest build when it was scanned against which database. |
| `data/mods.json` | The mods index. |
| `data/status/<source>.json` | Per source (manifests, releases, observed, mods, vulnerabilities): ok, checked_at, fetched_at, error. One file each, because the release path and the hourly refresh write different sources at the same time. |
| `data/status/rejected.json` | Releases whose bundle failed validation, with the error. Retried a day later, or as soon as the image's manifests change. |
| `data/status/bases.json` | Base image lookups that failed (a registry refusing, say), retried a day later instead of on every run. |

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
| `/api/v1/catalog/{name}/builds.json` | Builds in `data/` (newest first) with links, classification, `vulnerabilities` (the scan's counts, for builds that have one) and the release history per branch. `links.files` points at the hub's copy of `files.<arch>.json.gz` (same origin, newest build of each branch) and falls back to the Release asset, which `links.files_release` always carries. |
| `/api/v1/catalog/{name}/builds/{tag}.json` | The bundle record as received. |
| `/api/v1/catalog/{name}/builds/{tag}/report.json` | The build page aggregate: record facts, platforms, result, test summary per arch, diff summary (no package lists), notes and every link. One request per build page. |
| `/api/v1/catalog/{name}/builds/{tag}/tests.json` | The harness's `test.<arch>.json` per arch as received, with a summary (result, passed and failed tests, startup seconds, listening ports, warnings) and the report page URL. Only for builds that have a report. |
| `/api/v1/catalog/{name}/builds/{tag}/diff.json` | Packages per arch by ecosystem, config, base, size and Dockerfile changes, `classification`. |
| `/api/v1/catalog/{name}/builds/{tag}/vulns.json` | The vulnerability scan: `summary` (critical, high, medium, low, negligible, unknown, fixed, unfixed, wont_fix), `by_arch`, `matches` merged across architectures (one per id and package, with `arches`), `db_date`, `grype_version` and `caveats` (see below). Only for builds that have been scanned. |
| `/api/v1/catalog/{name}/builds/{tag}/packages.{arch}.json` | The package table; only for the newest build of each branch (older builds keep `packages.<arch>.json.gz` on the Release). |
| `/api/v1/catalog/{name}/builds/{tag}/layers.{arch}.json` | Layers with digest, size and Dockerfile instruction, plus `from_base` and `dockerfile_lines` (see below). |
| `/api/v1/catalog/{name}/mods.json`, `/api/v1/mods.json` | Mods for one image (its own, then universal), or all. |
| `/api/v1/catalog/{name}/proxy.json` | The SWAG subdomain and subfolder sample texts, reference configs for Caddy (`caddy`, a Caddyfile site block) and Traefik (`traefik`, compose labels) with the same upstream, open API paths and extra locations, and the manifest's `proxy` block. |
| `/api/v1/catalog/{name}/kubernetes.yaml`, `/quadlet.container` | Generated documents (only for images where `publish` enables them). |
| `/api/v1/packages.json`, `/api/v1/packages/{package}.json` | Every package name with its file slug; which images ship it, in which versions, per branch and arch. |
| `/api/v1/fleet/bases.json` | Base image references, the images on each, and the digests seen over time. |
| `/api/v1/fleet/staleness.json` | Newest builds whose base was seen newer elsewhere (a later digest in another build, or a later `baseimage-*` release when base images join the fleet). |
| `/api/v1/stores/index.json` | The six app stores (Unraid, Portainer, CasaOS, Umbrel, Runtipi, Cosmos), one import URL and a one-line how-to each. |

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

### Vulnerabilities

Every build scans itself: the shared workflow's publish job runs grype against both architectures' syft documents
and attaches the result to the Release in `record.json` (CONVENTIONS §6), and the ingest stores it. The hub then
keeps the scans current. The newest build of every live branch is scanned with [grype](https://github.com/anchore/grype) against the syft
document the build attached to its Release (`packages.<arch>.json.gz`, downloaded when there is no local copy in
`.cache/sboms/`), with `grype sbom:<file> -o json`. This is observed data: its clock is the vulnerability database,
not the build, so the same image gains and loses findings as the feeds move. The poller runs after `observe` in the
hourly refresh (`refresh.yml`), with a pinned grype binary and its database cached (`actions/cache`, one entry a day); it updates the
database at most once per 24 h and rescans a build only when the database date changed and its last scan is more
than 24 h old (a new build, or a missing architecture, is scanned at once), so the hourly run usually scans nothing.
Without grype or without a database nothing is scanned, the API builds without `vulns.json` files or summaries and
`data/status/vulnerabilities.json` says why. `data/observed.json` keeps the ledger.

How to read the numbers (the same sentences are served as `caveats`, so show them next to the counts):

- Counts are the scanner's output, not an assessment, and they change when the database changes, not only when the
  image does.
- Distribution packages (apk, deb) are matched against the distribution's own security feed, which knows about
  backported fixes: `fixed` means the distribution ships a fixed package version, `not-fixed` means no fix exists
  upstream for that distribution release. `unfixed` in the summary is everything neither fixed nor won't-fix (Alpine's
  feed often reports no fix state at all; the hub records `unknown`).
- Images are rebuilt weekly, so a distribution fix reaches the image within a week; a `fixed` finding on the newest
  build means that rebuild has not happened yet.
- Unfixable findings are not a reason to avoid an image: every image on the same base shares them, and only the
  distribution can resolve them. A finding against a package does not mean the vulnerable code path is reachable.

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
  playground repositories' real counts, which are 0 so far). The status endpoint reports `observed.json`'s
  `fetched_at` under `sources.observed`. `github_url`, `registries` and the docs link point at `linuxserver-playground` and
  `ghcr.io`; `Registries` has `ghcr` and `packages_url` only.
- `ImageDetail` dropped `docker_hub_pulls` and gained `title`, `upstream_version`, `base`, `releases` (one per
  live branch) and `links`.

## Generators

`python -m lsio_hub.generate` writes `out/stores/<platform>/` for every store and `out/builds/` for the
report pages; `--only a,b` limits the run and `--offline` skips Release downloads. Each generator is tested
against sonarr, swag and a constructed multi-arch image with an external database (`tests/fixtures/manifests/multidb.master.yml`).
`<hub>` below is the Pages site, `https://linuxserver-playground.github.io/hub`. Unraid, Umbrel and Runtipi read
a git repository and want the store's files at its root, so `refresh.yml` (its last steps, hourly, from the data
as of that run) pushes `out/stores/unraid/` to
`https://github.com/linuxserver-playground/unraid-store`, `out/stores/umbrel/` to
`https://github.com/linuxserver-playground/umbrel-store` and `out/stores/runtipi/` to
`https://github.com/linuxserver-playground/runtipi-store`
with `scripts/publish_store.sh`: the target's contents are replaced by the generated output plus a README saying
the repository is generated and how to import it, committed as `github-actions[bot]` (`Update generated store`)
only when something changed, pushed to `main` (created on an empty repository; the push is retried once after a
rebase). The token is an installation token of a GitHub App (`actions/create-github-app-token`, secrets
`STORE_APP_ID` and `STORE_APP_PRIVATE_KEY`) with `contents: write` on the three repositories. Those repository URLs
are the import URLs in `/api/v1/stores/index.json`.

| Generator | Output | Import |
| --- | --- | --- |
| `docs` | `images/docker-<name>.md` (builder's mkdocs docs template), `images-by-category.md` | Copy into the docs repository's `docs/`. |
| `unraid` | `<name>.xml`, `deprecated/<name>.xml` for `deprecation.status`, `ignore.list` for `publish.stores.unraid: false` | Unraid reads the root of `https://github.com/linuxserver-playground/unraid-store` (`<TemplateURL>` points there). Ported field for field from the legacy `unraid.xml.j2`; the icon is `docs.logo`, the WebUI comes from `test.web`, `publish.unraid.requirement` fills `<Requires>`. |
| `portainer` | `templates.json` (format version 3, type 1 templates) | Portainer → Settings → App Templates → URL: `<hub>/stores/portainer/templates.json`. |
| `casaos` | `Apps/<name>/docker-compose.yml` with `x-casaos`, `linuxserver.zip` | CasaOS → App Store → More apps → Add source: `<hub>/stores/casaos/linuxserver.zip`. |
| `umbrel` | `umbrel-app-store.yml` (`id: lsio`, `name`), `lsio-<name>/umbrel-app.yml` (the template's fields: `manifestVersion`, `id`, `category`, `name`, `tagline`, `icon`, `version`, `description`, `developer`, `website`, `repo`, `support`, `port`, `gallery`, `releaseNotes`, `path`, ...), `docker-compose.yml` (app_proxy with `APP_HOST: lsio-<name>_server_1`, data under `APP_DATA_DIR`), `exports.sh` | Umbrel → App Store → Community App Stores → `https://github.com/linuxserver-playground/umbrel-store`. Layout as `getumbrel/umbrel-community-app-store`: app directories named `<store id>-<app>` at the repository root. |
| `runtipi` | `apps/<name>/config.json`, `docker-compose.yml` in the dynamic compose format (top-level `x-runtipi: {schema_version: 2}`, the main service with `x-runtipi: {is_main, internal_port}`; Runtipi adds the `${APP_PORT}` mapping, Traefik labels and network itself), `metadata/description.md` | Runtipi → Settings → App Stores → Add App Store → `https://github.com/linuxserver-playground/runtipi-store`. `apps/` at the repository root, the folder name being the app `id`. Runtipi wants `metadata/logo.jpg` as a file; the hub does not copy logos into git, so `config.json` carries `logo_url` (`docs.logo`) and the description page embeds it. |
| `cosmos` | `index.json` (`source`, `showcase`, `all`), `servapps/<name>/description.json`, `cosmos-compose.json` | Cosmos → Market → Sources → `<hub>/stores/cosmos/index.json`. Matches the TinyActive community source (fetched 2026-10-24). |
| `proxy` | `<name>.subdomain.conf.sample`, `<name>.subfolder.conf.sample`, `README.md` | The proxy-confs repository; SWAG pulls it into `/config/nginx/proxy-confs/`. Reproduces the live sonarr samples: auth includes as comments, `api_locations` without auth, websocket upgrade headers when `websocket`, `extra_locations`, `notes` as header comments. |
| `kubernetes` | `<name>.yaml`: ConfigMap, PVC per `publish.kubernetes.persistence` (default: required volumes), Deployment or StatefulSet, Service; security notes as comments | `kubectl apply -f <hub>/stores/kubernetes/<name>.yaml` after editing storage sizes. |
| `quadlet` | `<name>.container` | Copy to `~/.config/containers/systemd/`, `systemctl --user daemon-reload`. |
| `mods` | `mod-list.yml` in the legacy shape | `<hub>/stores/mods/mod-list.yml`; the structured index is `/api/v1/mods.json`. |
| `builds` | see below | `<hub>/builds/<image>/<tag>/` |

The mods index reads `mod.yml` from every branch of `linuxserver-playground/docker-mods` (`master` and
`template` excepted); each entry's image is `ghcr.io/linuxserver-playground/mods:<target>-<name>`. A mod's
`applies_to` is its target followed by the images its `mod.yml` lists under `images`, the curated list that
replaced the legacy `mod-list.yml`. `/api/v1/catalog/<image>/mods.json` gives an image's own mods first, then the
universal mods curated for it, then every other universal mod. A branch whose `mod.yml` is missing or fails the
schema is logged and left out.

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
4. Pushing the stores (`refresh.yml`) needs the `STORE_APP_ID` and `STORE_APP_PRIVATE_KEY` secrets: a GitHub App
   installed on the organisation with `contents: write` on `unraid-store`, `umbrel-store` and `runtipi-store`. Without
   them those steps are skipped and the Pages deployment is unaffected.
5. The grype binary is pinned in `refresh.yml` (version and sha256); bump both together. Its database is a few GB on
   disk and lives in the Actions cache under `grype-db-<date>`.

## Notes on the contracts

- `CONVENTIONS.md §3` says a Release's `target_commitish` is the branch name; the shared workflow currently
  writes the commit sha. The hub guesses the branch from the tag prefix and verifies it against `branch` in the
  bundle, rejecting bundles for non-live branches.
- `lsio-builder` pins `jsonschema==4.25.1` and `referencing==0.36.2` exactly, which rules out
  `openapi-spec-validator>=0.8`; the dev dependency is pinned to 0.7.2.
- `lsio-builder` ships no `py.typed`, so `mypy --strict` treats it as untyped (see `pyproject.toml`).
