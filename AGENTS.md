# AGENTS.md - hub

## Purpose

The hub is the data nexus of the LinuxServer v2 playground. It ingests the build bundle every image release
attaches to its GitHub Release, keeps that data in git on the `data` branch (one commit, no history; checked out
as `data/`), serves a static API on GitHub Pages
(`/api/v1/...`), and generates every downstream artefact: docs pages, store templates (Unraid, Portainer,
CasaOS, Umbrel, Runtipi, Cosmos), SWAG proxy confs, Kubernetes manifests, Podman quadlets, the mods index
and redirects from the retired build report pages (`/builds/<image>/<tag>/`) to each build's page on the website. It
holds the newest 5 builds per live branch, as each image repository's own Pages does, and copies none of their heavy
files (screenshots, logs, file trees, SBOMs, the vulnerability scan): those are on
`https://<owner>.github.io/<repo>/builds/<tag>/`, deployed by the image's build, and the API links there
(`config.repo_pages`, the one place that URL is derived). A build's vulnerability scan is the one it made of itself
when it was released (record.json); the hub keeps only its counts and never rescans. Release assets send no CORS headers, so the API offers them
only as download links, never as something a browser fetches. Consumers: the docs and stores repositories, the
site, the control plane (which reads the API to hold Discord until a build is served), and anyone using the API.

## Layout

| Path | What |
| --- | --- |
| `lsio_hub/models.py` | Every response shape (pydantic). The v1 models are the original API's, field for field. |
| `lsio_hub/store.py` | The `data/` layout: load and save, rotation-aware. |
| `lsio_hub/ingest.py`, `observe.py`, `mods.py` | Writers of `data/`: bundles, manifests and the counts of each build's own scan, stars and archived flags, the mods index. |
| `lsio_hub/diff.py`, `packages.py` | The build diff engine and the syft package normaliser (both re-export `builder.derive`, which the build runs for its `record.json`). Layer attribution and the shape of every per-build document (report, tests, layers) are `builder.derive.layers` and `builder.derive.documents`, which `responses.py` renders with and the pages assembler in workflows also writes copies with. |
| `lsio_hub/transform.py`, `fleet.py`, `responses.py` | Manifests and builds to API images; the content of each endpoint. |
| `lsio_hub/app.py`, `build.py`, `site.py`, `templates/` | The FastAPI app, the static build of `dist/`, the docs page. |
| `lsio_hub/generate/` | One module per generator; `python -m lsio_hub.generate` writes `out/`. |
| `scripts/commit_data.sh`, `scripts/data.sh` | Publish `data/` as the `data` branch's one commit, merging with a concurrent writer (CI only); fetch it into `data/` locally. |
| `scripts/publish_store.sh` | Pushes `out/stores/umbrel/` and `out/stores/runtipi/` to their own repositories (the last steps of the hourly `refresh.yml`). |
| `lsio_hub/sources/` | GitHub REST/GraphQL, GHCR, retrying HTTP. |
| `data/` | A depth-1 checkout of the `data` branch (`scripts/data.sh`), not part of `main`. Written only by the ingest (manifests, bundles, `bases/`), the observer and the mods refresh, and published by `scripts/commit_data.sh`, which replaces the branch's one commit. |
| `tests/` | pytest; `tests/fixtures/` holds live manifests, a real release's small assets and reference outputs. |

## What you may edit

Everything under `lsio_hub/`, `tests/`, `public/`, `scripts/` (shellcheck clean), `.github/`, this file and the README. Do not hand-edit
`data/` (CI overwrites it; use the ingest commands), and never commit `dist/` or `out/`. A new endpoint needs
a model, a response builder, a route, and a line in the README's endpoint table. A generator change needs
its fixture test updated for sonarr, swag and the constructed `multidb` image.

## How to validate

```bash
python3.13 -m venv .venv && . .venv/bin/activate
pip install -e '.[dev]'                      # pulls lsio-builder from linuxserver-playground/builder
scripts/data.sh                              # data/ from the data branch (again to update it)
ruff check . && ruff format --check . && mypy && pytest
python -m lsio_hub.build                     # dist/ from the published data
python -m lsio_hub.generate                  # out/ from the published data (downloads nothing)
GITHUB_TOKEN=$(gh auth token) python -m lsio_hub.ingest --reconcile   # refresh data/ (reads only)
```

## Contracts

Consumes, from `linuxserver-playground/builder`: `image.schema.json` (every manifest is validated on
ingest), `bundle.schema.json` (every `build.json`; invalid bundles are recorded in
`data/status/rejected.json` and retried a day later), `test-report.schema.json` (`test.<arch>.json`), `record.schema.json` (`record.json`, what the build derived for
the hub; ingested instead of deriving when a release has one), `mod.schema.json` (`mod.yml` per
docker-mods branch), and `builder.snippets` / `builder.render` for compose, run and docs output. Produces
no schema of its own; the API's shapes are the pydantic models and the generated `openapi.json`. See
`CONVENTIONS.md` in the builder repository.

## Pull request rules

Disclose AI use. One change per PR. Commit subjects are short imperative sentences without prefixes,
emoji or trailers. Do not commit generated output or credentials. Only CI publishes the `data` branch
(`scripts/commit_data.sh`); never push to it by hand, and never add `data/` back to `main`.
