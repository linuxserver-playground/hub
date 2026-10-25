# AGENTS.md - hub

## Purpose

The hub is the data nexus of the LinuxServer v2 playground. It ingests the build bundle every image release
attaches to its GitHub Release, keeps that data in git under `data/`, serves a static API on GitHub Pages
(`/api/v1/...`), and generates every downstream artefact: docs pages, store templates (Unraid, Portainer,
CasaOS, Umbrel, Runtipi, Cosmos), SWAG proxy confs, Kubernetes manifests, Podman quadlets, the mods index
and the CI build report pages (`/builds/<image>/<tag>/`). Consumers: the docs and stores repositories, the
site, the control plane (which links to the build pages), and anyone using the API.

## Layout

| Path | What |
| --- | --- |
| `lsio_hub/models.py` | Every response shape (pydantic). The v1 models are the original API's, field for field. |
| `lsio_hub/store.py` | The `data/` layout: load and save, rotation-aware. |
| `lsio_hub/ingest.py`, `observe.py`, `vulns.py`, `mods.py` | Writers of `data/`: bundles and manifests, stars and GHCR tags, the grype scan of the newest builds, the mods index. |
| `lsio_hub/diff.py`, `packages.py`, `layers.py` | The build diff engine, the syft package normaliser, layer attribution (`from_base`, `dockerfile_lines`). |
| `lsio_hub/transform.py`, `fleet.py`, `responses.py` | Manifests and builds to API images; the content of each endpoint. |
| `lsio_hub/app.py`, `build.py`, `site.py`, `templates/` | The FastAPI app, the static build of `dist/`, the docs page. |
| `lsio_hub/generate/` | One module per generator; `python -m lsio_hub.generate` writes `out/`. |
| `scripts/publish_store.sh` | Pushes `out/stores/umbrel/` and `out/stores/runtipi/` to their own repositories (deploy.yml's `publish-stores` job). |
| `lsio_hub/sources/` | GitHub REST/GraphQL, GHCR, retrying HTTP. |
| `data/` | Committed data, written only by the ingest (manifests, bundles, `bases/`), the observer and the mods refresh. |
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
ruff check . && ruff format --check . && mypy && pytest
python -m lsio_hub.build                     # dist/ from the committed data
python -m lsio_hub.generate --offline        # out/ from the committed data, no Release downloads
GITHUB_TOKEN=$(gh auth token) python -m lsio_hub.ingest --reconcile   # refresh data/ (reads only)
```

## Contracts

Consumes, from `linuxserver-playground/builder`: `image.schema.json` (every manifest is validated on
ingest), `bundle.schema.json` (every `build.json`; invalid bundles are recorded in `data/status.json` under
`rejected` and skipped), `test-report.schema.json` (`test.<arch>.json`), `mod.schema.json` (`mod.yml` per
docker-mods branch), and `builder.snippets` / `builder.render` for compose, run and docs output. Produces
no schema of its own; the API's shapes are the pydantic models and the generated `openapi.json`. See
`CONVENTIONS.md` in the builder repository.

## Pull request rules

Disclose AI use. One change per PR. Commit subjects are short imperative sentences without prefixes,
emoji or trailers. Do not commit generated output or credentials. Data commits are made by CI as
`Update data`.
