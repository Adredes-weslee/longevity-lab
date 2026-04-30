# Longevity Lab

Longevity Lab is a local-first product prototype for interactive organ-level lifestyle risk communication, built on public health data, calibrated interpretable models, and a React + FastAPI interface.

## Project status

This repo is intentionally usable *today* (end-to-end UI <-> API), and it now includes a real local training/evaluation path for tree-based artifact bundles.

- Current state: typed API + runnable UI + explicit compare/apply UX + a reference-based silhouette
  heatmap + BRFSS/EPA pipeline + Hydra/Optuna training entrypoints that write calibrated per-condition
  artifact bundles with metrics, prediction samples, and explanation trees.
- Default serving mode is `auto`: the backend uses a valid local artifact bundle when present and
  otherwise falls back to clearly labeled demo scoring.
- Target end state: BRFSS/EPA ingest -> trained + calibrated tree models -> artifact-backed API by
  default -> organ UI with richer typed explanations.
- Product expansion roadmap: `docs/roadmap.md`
- PR execution plan: `docs/superpowers/plans/2026-04-30-longevity-lab-expansion.md`
- TODO tracker: `docs/feature_status.md`

## Stack

- `frontend/`: Vite + React + TypeScript + D3 utilities
- `src/longevity_lab/`: FastAPI API, domain model, pipeline stubs, demo inference engine
- `data/`: raw/processed/sample data layout
- `docs/`: architecture, roadmap, contracts, and implementation plans
  - Feature tracker: `docs/feature_status.md`
  - Product roadmap: `docs/roadmap.md`
  - Superpowers PR plan: `docs/superpowers/plans/2026-04-30-longevity-lab-expansion.md`

## Why this repo is structured this way

- The data pipeline, model artifacts, organ mappings, and UI contracts are tightly coupled.
- A single repo keeps schemas, docs, and boilerplate in one place without monorepo tooling overhead.

## Quick start

Start here if you are new to the repo:

1. Read `docs/quickstart.md` for the full developer flow.
2. Read `CONTRIBUTING.md` + `docs/git_workflow.md` before opening a PR.
3. Use `docs/feature_status.md` to find the next work item and check what is real vs demo.

### Prereqs

- Python 3.12+
- PDM 2.26+ (`pipx install pdm`)
- Node.js 22+ (npm 10+)

### Backend

Optional: copy `.env.example` to `.env` to override local settings (engine selection, paths).
If your frontend runs on a different port, update `LONGEVITY_LAB_CORS_ALLOW_ORIGINS` (no `*`).
If you use the Vite `/api` proxy (default), you can also set it empty to disable CORS.

PowerShell:

```powershell
pdm install -G dev
pdm run python -m uvicorn longevity_lab.api.main:app --reload
```

bash/zsh:

```bash
pdm install -G dev
pdm run python -m uvicorn longevity_lab.api.main:app --reload
```

Verify:

```powershell
curl.exe http://127.0.0.1:8000/api/health
```

bash/zsh:

```bash
curl http://127.0.0.1:8000/api/health
```

### Frontend

PowerShell:

```powershell
cd frontend
npm ci
npm run dev
```

bash/zsh:

```bash
cd frontend
npm ci
npm run dev
```

The Vite dev server proxies `/api` to `http://localhost:8000`.

See `docs/quickstart.md` for common workflows (tests, lint, running both).

### Launch the dashboard

- Explorer view: `http://localhost:5173/`
- Data integration view: `http://localhost:5173/#/data`

Use the Explorer page for the organ heatmap + drill-down flow. Current and what-if inputs stay
visible side by side, and the scores update live as sliders move. Use the `Delta | Baseline |
Scenario` toggle to switch the body view.
Use the Data integration page to verify whether BRFSS/EPA raw and processed artifacts exist locally.

### Run all checks

PowerShell:

```powershell
.\scripts\check_all.ps1
```

bash/zsh:

```bash
bash scripts/check_all.sh
```

## E2E smoke test (Playwright)

```powershell
cd frontend
npm run test:e2e
```

Current smoke coverage:

- app loads and renders the compare flow
- organ drill-down opens from the heatmap/callout interaction
- heatmap mode toggle switches between delta and absolute views
- numeric inputs clamp to supported ranges
- live slider edits update results automatically
- stale comparison results clear correctly after a failed compare request

## Training and evaluation

Install the training extras before running the model pipeline:

```powershell
pdm install -G dev -G train
```

Train a calibrated bundle from the integrated 2023 table:

```powershell
pdm run python -m longevity_lab.pipeline.train
```

Summarize the latest bundle:

```powershell
pdm run python -m longevity_lab.pipeline.evaluate
```

Write report-ready overall + subgroup metrics:

```powershell
pdm run python -m longevity_lab.pipeline.evaluate artifacts.output_path=artifacts/models/eval-summary.json artifacts.slice_output_path=artifacts/models/eval-slices.json
```

The API auto-detects a valid local bundle by default. To require artifact mode and fail fast when
no valid bundle exists, set:

```powershell
$env:LONGEVITY_LAB_ENGINE='artifact'
```

Optional:

```powershell
$env:LONGEVITY_LAB_ARTIFACT_BUNDLE='bundle-20260326-real'
```

Bundled outputs are written under `artifacts/models/<bundle_id>/` (gitignored) and include:

- `manifest.json`
- `training_summary.json`
- per-condition calibrated pipelines, explanation pipelines, metrics JSONs, prediction Parquet files,
  feature-importance JSONs, and tree text dumps

## Analysis reports

The product roadmap moves analysis evidence from notebooks into scripted reports that write metrics,
figures, tables, and model cards programmatically. Legacy notebooks from the project prototype are
kept outside tracked source under `legacy_artifacts/`.

## Repo layout

```text
frontend/                 React UI
src/longevity_lab/        Python package
  api/                    FastAPI app and routes
  domain/                 Typed domain definitions
  services/               Metadata and scenario services
  pipeline/               Data ingest, training, and evaluation entrypoints
tests/                    Backend tests
data/
  sample/                 Small checked-in demo assets only
  external/               Ignored raw public datasets
  processed/              Ignored derived tables and snapshots
artifacts/
  models/                 Ignored trained model artifacts
docs/                     Architecture, roadmap, contracts, and implementation plans
```

## Current scope

This scaffold intentionally ships with:

- a typed FastAPI backend,
- a runnable React frontend,
- a deterministic demo scenario engine,
- BRFSS/EPA ingest + integration pipeline scripts (to `data/processed/`, gitignored).

It does **not** commit trained model artifacts or final polished anatomical art assets. Trained bundles
are produced locally under `artifacts/models/` and are intentionally gitignored.

## Pipeline (download + build)

This writes raw data to `data/external/` and derived tables to `data/processed/` (both gitignored).
If you skip this, the app still runs, but the UI's **Data integration** page will show the expected artifacts as "Missing".

These CLIs default to the repo-root `data/` directory even if you run them from `frontend/` or
another subdirectory.

```powershell
pdm run python -m longevity_lab.pipeline.download_brfss --year 2023
pdm run python -m longevity_lab.pipeline.download_epa_airdata --year 2023
pdm run python -m longevity_lab.pipeline.build_brfss_tables --year 2023
pdm run python -m longevity_lab.pipeline.build_epa_tables --year 2023
pdm run python -m longevity_lab.pipeline.build_integrated_tables --year 2023
pdm run python -m longevity_lab.pipeline.build_duckdb_views
```

Note: EPA 2023 does not include a Guam state row. The integrated build keeps those BRFSS rows with
`annual_aqi = null` by default and still raises for unexpected missing joins.

Verify:

```powershell
curl.exe http://127.0.0.1:8000/api/pipeline/status?year=2023
```

## Documentation map

- Start here: `docs/quickstart.md`
- Feature/TODO tracker: `docs/feature_status.md`
- Contributing guidelines: `CONTRIBUTING.md` + `docs/git_workflow.md`
- Dataset sources + download notes: `docs/datasets.md`
- Data dictionary (fields + transformations): `docs/data_dictionary.md`
- Schema contracts (tables/views): `docs/schema_contracts.md`
- Architecture rationale: `docs/architecture.md`
- Baseline implementation history: `docs/implementation_plan.md`
- Git workflow: `docs/git_workflow.md`
- Developer quickstart: `docs/quickstart.md`
