# Quickstart (dev workflow)

This guide is meant to get a developer productive quickly.

## First-day checklist

1. Install Python 3.12+, PDM, Node.js 22+, and npm 10+.
2. From the repo root, run the one-command bootstrap for your shell.
3. Optionally copy `.env.example` to `.env` for local overrides.
4. Run the dashboard once, then run the smoke checks.

PowerShell:

```powershell
.\scripts\bootstrap_dev.ps1
```

bash/zsh:

```bash
bash scripts/bootstrap_dev.sh
```

The bootstrap installs backend dev and training dependencies plus frontend lockfile dependencies by
default, because the repository checks type-check training entrypoints. For optional SHAP/notebook
work, add the relevant extras:

```powershell
.\scripts\bootstrap_dev.ps1 -Explainability -Notebook
```

bash/zsh:

```bash
bash scripts/bootstrap_dev.sh --explainability --notebook
```

## Run the app (2 terminals)

Optional: copy `.env.example` to `.env` to override local settings.
By default, `LONGEVITY_LAB_ENGINE=auto` loads a valid trained bundle from `artifacts/models/`
when one exists and otherwise falls back to clearly labeled demo scoring.
Set `LONGEVITY_LAB_ENGINE=artifact` only when you want startup to require a valid local bundle.
If your frontend runs on a different port, update `LONGEVITY_LAB_CORS_ALLOW_ORIGINS` (comma-separated, no `*`).
If you use the Vite `/api` proxy (default), you can also set it empty to disable CORS.

Terminal A (backend, after bootstrap):

```powershell
pdm run python -m uvicorn longevity_lab.api.main:app --reload
```

bash/zsh:

```bash
pdm run python -m uvicorn longevity_lab.api.main:app --reload
```

Terminal B (frontend, after bootstrap):

```powershell
cd frontend
npm run dev
```

bash/zsh:

```bash
cd frontend
npm run dev
```

Open the Vite URL (usually `http://localhost:5173`).

Useful routes:

- Explorer: `http://localhost:5173/`
- Data Evidence: `http://localhost:5173/#/data`
- Community Context: `http://localhost:5173/#/community`
- Model Cards: `http://localhost:5173/#/models`
- Scenario Lab: `http://localhost:5173/#/lab`

Tip: the UI includes a separate **Data Evidence** page that calls `GET /api/pipeline/status`
to show whether expected raw/processed pipeline artifacts exist locally.
The **Community Context** page uses `GET /api/community/overview` to show ACS/SVI, PLACES, and
causal-workbench evidence as background/research context; it does not change Explorer personal
scores.

## Quick smoke check after startup

1. Open the Explorer page and confirm the baseline/scenario summaries render.
2. Click an organ or callout and confirm the drill-down updates.
3. Open `#/data` and confirm the pipeline status page loads.
4. Open `#/community` and confirm context/PLACES/causal cards load or degrade with explicit unavailable states.
5. Open `#/models` and confirm active model metadata plus model-card metrics are visible when an artifact bundle is active.

## Intended use and safety language

Longevity Lab is an educational, non-diagnostic risk-communication app. It is suitable for
inspecting model provenance and comparing broad predictive scenario patterns. It is not suitable
for diagnosis, screening, treatment decisions, emergency triage, insurance/employment decisions, or
individual eligibility decisions.

Explorer scenario deltas are predictive model comparisons, not causal estimates. Public-health
links are general cited guidance, not personalized medical advice. Geography and environmental
fields are background context where available, not personal behaviors.

Artifact bundles are trusted local outputs only. Do not load model bundles from unknown sources:
Python/joblib artifacts can execute code during deserialization. Production downloads should use
known release URLs plus SHA256 verification, and local development should keep raw data and trained
artifacts in gitignored directories.

## Backend checks

```powershell
pdm run ruff check src tests
pdm run ruff format --check src tests
pdm run mypy src tests
pdm run pytest
```

bash/zsh:

```bash
pdm run ruff check src tests
pdm run ruff format --check src tests
pdm run mypy src tests
pdm run pytest
```

## Train and evaluate a local model bundle

Install the training extras first:

```powershell
pdm install -G dev -G train
```

Train the default calibrated decision-tree baseline bundle:

```powershell
pdm run python -m longevity_lab.pipeline.train
```

Review the latest bundle summary:

```powershell
pdm run python -m longevity_lab.pipeline.evaluate
```

Write report-ready summary + subgroup slice exports:

```powershell
pdm run python -m longevity_lab.pipeline.evaluate artifacts.output_path=artifacts/models/eval-summary.json artifacts.slice_output_path=artifacts/models/eval-slices.json
```

The API serves a valid local bundle automatically when `LONGEVITY_LAB_ENGINE=auto`.
Model-card metrics for the active bundle are exposed through `GET /api/models/cards`.
To require artifact mode explicitly:

```powershell
$env:LONGEVITY_LAB_ENGINE='artifact'
pdm run python -m uvicorn longevity_lab.api.main:app --reload
```

Optional: pin a specific local bundle id with `LONGEVITY_LAB_ARTIFACT_BUNDLE`.

The training pipeline writes gitignored outputs under `artifacts/models/<bundle_id>/`, including:

- `manifest.json`
- `training_summary.json`
- per-condition metrics JSONs
- per-condition prediction Parquet files
- per-condition explanation tree artifacts

The current public demo deployment uses the separately published
`real-20260508-xgboost-shap` artifact rather than the default local decision-tree baseline. Use the
benchmark and artifact-promotion workflow in `docs/modeling.md` when you need to reproduce or
replace that production bundle.

## Frontend checks

```powershell
cd frontend
npm run check
npm run lint
npm run build
```

## Run all checks

PowerShell:

```powershell
.\scripts\check_all.ps1
```

bash/zsh:

```bash
bash scripts/check_all.sh
```

## E2E smoke test (Playwright)

From `frontend/`, `npm run test:e2e` will start (or reuse) both the backend and frontend dev servers
and run a small UI smoke test.

```bash
bash scripts/bootstrap_dev.sh
cd frontend
npm run test:e2e
```

## Build the datasets (optional, for pipeline/modeling work)

This downloads raw datasets into `data/external/` and writes processed tables into `data/processed/`
(both gitignored).

If you skip this, the app still runs, but the UI's **Data Evidence** page will show "Missing" for the expected artifacts.

These CLIs now default to the repo-root `data/` directory even if you run them from `frontend/` or
another subdirectory.

```powershell
pdm run python -m longevity_lab.pipeline.download_brfss --year 2023
pdm run python -m longevity_lab.pipeline.download_epa_airdata --year 2023
pdm run python -m longevity_lab.pipeline.download_acs --year 2022
pdm run python -m longevity_lab.pipeline.download_svi --year 2022
pdm run python -m longevity_lab.pipeline.download_places --year 2025
pdm run python -m longevity_lab.pipeline.build_brfss_tables --year 2023
pdm run python -m longevity_lab.pipeline.build_epa_tables --year 2023
pdm run python -m longevity_lab.pipeline.build_context_tables --year 2022
pdm run python -m longevity_lab.pipeline.build_places_tables --year 2025
pdm run python -m longevity_lab.pipeline.build_integrated_tables --year 2023 --context-year 2022
pdm run python -m longevity_lab.pipeline.build_duckdb_views
```

Note: EPA 2023 does not include a Guam state row. The integrated build now keeps those BRFSS rows
with `annual_aqi = null` by default and still raises for unexpected missing joins.
SVI is currently registry-supported through the 2022 release, while PLACES uses the 2025 county
release. The integrated 2023 table uses `--context-year 2022` to record that ACS/SVI context vintage
explicitly in `context_data_year` instead of silently pretending it is 2023 context.

Verify:

```powershell
curl.exe http://127.0.0.1:8000/api/pipeline/status?year=2023
```

Recommended local verification after building:

1. Open `http://localhost:5173/#/data`
2. Confirm BRFSS/EPA/ACS/SVI/PLACES/integrated/DuckDB artifacts show as `Ready`
3. Confirm provenance summaries are populated

Notes:

- BRFSS scripts are pinned to 2023 for v1 (see `docs/datasets.md`).
- EPA scripts support `--years` (e.g., `--years 2021,2022,2023`) but the integrated table requires the
  matching BRFSS processed table for each year.

## Run the analysis notebook

Install the notebook extras when you want the Jupyter workflow:

```powershell
pdm install -G dev -G train -G notebook
pdm run python -m jupyter lab
```

Open `ml_pipeline_analysis.ipynb` from the repo root. The notebook now:

- verifies the raw/processed artifact layout
- profiles the integrated table
- reads the latest local training bundle
- plots calibrated metrics and the `annual_aqi` ablation
- breaks performance down by subgroup / slice
- exercises scenario compare through the current service layer

## Where to start contributing

1. Pick a `TODO` in `docs/feature_status.md`.
2. Keep the touch set small (one area: pipeline/backend/frontend/docs).
3. Update the tracker when the status changes (`TODO` -> `STUB` -> `DEMO` -> `DONE`).
4. Update docs if your change affects setup, routes, scripts, or expected outputs.

## Recommended: install pre-commit (Python formatting + lint)

```powershell
pdm run pre-commit install
```

## Notes on data and artifacts

- Raw datasets belong in `data/external/` (gitignored).
- Processed tables belong in `data/processed/` (gitignored).
- Trained models belong in `artifacts/models/` (gitignored).
- If you need to commit data for dev/testing, keep it tiny and legal in `data/sample/`.
- Dataset sources and download notes: `docs/datasets.md`.
