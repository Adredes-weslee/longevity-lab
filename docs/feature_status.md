# Feature Status

This document is the source of truth for implemented product surfaces and planned work.

Legend:
- [DONE] `DONE`: implemented and working
- [DEMO] `DEMO`: implemented but backed by demo/scaffold logic
- [STUB] `STUB`: entrypoint exists but does not do real work yet
- [TODO] `TODO`: not started

## Product roadmap status

- [DONE] Governance, roadmap, local overlay, worktree policy, and PR plan drafted.
- [TODO] Artifact-first runtime default when a valid local bundle exists.
- [TODO] Data source registry and provenance schema for additional public sources.
- [TODO] BRFSS v2 feature contract with survey weights and broader adjustment covariates.
- [TODO] EPA pollutant-specific features beyond annual AQI.
- [TODO] ACS/SVI contextual social-determinants features.
- [TODO] CDC PLACES contextual validation layer.
- [TODO] Scripted EDA/report generation to replace notebooks as canonical outputs.
- [TODO] Modeling benchmark harness and calibrated gradient-boosted model family.
- [TODO] Typed explanation, uncertainty, and model-card surfaces.
- [TODO] Separate causal inference specification and workbench.
- [TODO] UI information architecture, Explorer upgrade, and deployment packaging.

## Current baseline

### Core user workflow

- [DONE] UI loads metadata and default scenarios (`frontend/src/App.tsx`).
- [DONE] User edits current and what-if inputs side by side with live compare updates (`frontend/src/components/scenario-form.tsx`).
- [DONE] UI calls compare endpoint and renders results (`frontend/src/api/client.ts`).
- [DEMO] Organ heatmap renders delta, baseline, and scenario views with callouts (`frontend/src/components/body-heatmap.tsx`).
- [DEMO] Drill-down shows condition probabilities, drivers, citations, and guidance (`frontend/src/components/condition-inspector.tsx`).
- [DONE] Backend exposes stable typed contract (`src/longevity_lab/api/schemas.py`).
- [DEMO] Backend compares two scenarios through `POST /api/scenario/compare` (`src/longevity_lab/api/routes/scenario.py`).

### Data pipeline

- [DONE] Dataset directory layout and typed path builder (`src/longevity_lab/pipeline/ingest.py`).
- [DONE] BRFSS download script with provenance (`src/longevity_lab/pipeline/download_brfss.py`).
- [DONE] BRFSS decode and Parquet build for v1 columns (`src/longevity_lab/pipeline/build_brfss_tables.py`).
- [DONE] EPA AirData annual AQI download and preprocessing (`src/longevity_lab/pipeline/download_epa_airdata.py`, `src/longevity_lab/pipeline/build_epa_tables.py`).
- [DONE] BRFSS/EPA state-year join (`src/longevity_lab/pipeline/build_integrated_tables.py`).
- [DONE] Expected EPA territory coverage gaps handled without breaking integrated builds (`src/longevity_lab/pipeline/build_integrated_tables.py`).
- [DONE] Small sample slice committed in `data/sample/` for dev/testing only.
- [DONE] DuckDB stable views builder (`src/longevity_lab/pipeline/build_duckdb_views.py`).
- [DONE] Pipeline CLIs default to repo-root `data/` even when invoked from subdirectories (`src/longevity_lab/pipeline/common.py`).

### Modeling

- [DONE] Hydra-based training entrypoint (`src/longevity_lab/pipeline/train.py`, `conf/train.yaml`).
- [DEMO] Demo risk engine (`src/longevity_lab/services/scenario_service.py`).
- [DONE] Decision-tree baseline per condition with Optuna tuning (`src/longevity_lab/pipeline/modeling.py`).
- [DONE] Calibration for probability outputs (`src/longevity_lab/pipeline/modeling.py`).
- [DONE] Evaluation script and metrics report scaffold (`src/longevity_lab/pipeline/evaluate.py`).
- [DONE] Subgroup/slice analysis export for trained bundles (`src/longevity_lab/pipeline/evaluate.py`, `src/longevity_lab/pipeline/modeling.py`).
- [DONE] Artifact manifest schema and bundle loader (`src/longevity_lab/artifacts/manifest.py`, `src/longevity_lab/artifacts/store.py`).
- [DONE] Explanation outputs aligned to saved explanation trees (`src/longevity_lab/services/artifact_engine.py`).

### Backend/API

- [DONE] Health check (`GET /api/health`) (`src/longevity_lab/api/routes/health.py`).
- [DONE] Metadata bootstrap (`GET /api/metadata/bootstrap`) (`src/longevity_lab/api/routes/metadata.py`).
- [DONE] Pipeline status endpoint (`GET /api/pipeline/status`) (`src/longevity_lab/api/routes/pipeline.py`).
- [DONE] Service layer and engine abstraction (`src/longevity_lab/services/scenario_service.py`).
- [DONE] Artifact-backed engine path (`src/longevity_lab/services/artifact_engine.py`).
- [DONE] Input validation and safe defaults for missing features.
- [DONE] Structured logging and request IDs.

### Frontend UX

- [DEMO] Body map uses a reference-based silhouette underlay plus SVG organ overlays.
- [DONE] Explorer layout includes side-by-side current and what-if inputs, a persistent comparison strip, and absolute-risk versus relative-change legends.
- [DONE] Scenario editing is live and updates the evaluation snapshot automatically.
- [DONE] High-risk drill-down panels surface public-health guidance links when either current or what-if profile is in the red band.
- [DONE] Explorer view shows a compact non-diagnostic disclaimer.
- [TODO] Better "what changed" deltas per organ/condition.
- [DEMO] Basic accessibility pass.
- [DEMO] Mobile/responsive layout pass.

### Reproducibility

- [DONE] Backend tests (`tests/`).
- [DONE] Python type-check and lint configured (`pyproject.toml`).
- [DONE] Frontend lint/type/build configured (`frontend/`).
- [DONE] CI workflow (`.github/workflows/ci.yml`).
- [DONE] One-command dev checks (`scripts/check_all.ps1`, `scripts/check_all.sh`).
- [DONE] E2E smoke tests (`frontend/e2e/`).
- [TODO] One-command dev bootstrap for Windows and macOS.
- [DONE] Artifact-backed runtime no longer requires Optuna just to load packaged bundles (`src/longevity_lab/pipeline/modeling.py`).
- [DONE] Dataset sources and provenance docs (`docs/datasets.md`, `docs/data_dictionary.md`).
- [TODO] Finalize ethics and health disclaimer language across the UI and documentation.

## Highest-ROI next tasks

1. Make artifact mode the default when a valid local bundle is present.
2. Add the public data-source registry.
3. Add BRFSS v2 and contextual data feature contracts.
4. Replace notebook-derived analysis with scripted reports.
5. Start the modeling benchmark harness.
