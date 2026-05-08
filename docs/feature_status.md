# Feature Status

This document is the source of truth for implemented product surfaces and planned work.

Legend:
- [DONE] `DONE`: implemented and working
- [DEMO] `DEMO`: implemented but backed by demo/scaffold logic
- [STUB] `STUB`: entrypoint exists but does not do real work yet
- [TODO] `TODO`: not started

## Product roadmap status

- [DONE] Governance, roadmap, local overlay, worktree policy, and PR plan drafted.
- [DONE] Artifact-first runtime default when a valid local bundle exists.
- [DONE] Model-card endpoint and UI metrics surface for active artifact bundles.
- [DONE] Evidence-status endpoint and UI separate active scoring inputs from local-only data, validation reports, and inactive geography context.
- [DONE] Data source registry and provenance schema for current public sources.
- [DONE] BRFSS v2 feature contract with survey weights and broader adjustment covariates.
- [DONE] EPA pollutant-specific features beyond annual AQI.
- [DONE] ACS/SVI contextual social-determinants features.
- [DONE] CDC PLACES contextual validation layer.
- [DONE] Optional data-source candidate screen for AHRQ, USDA, County Health Rankings, CDC WONDER, NHANES, and NHIS.
- [DONE] Scripted EDA/report generation to replace notebooks as canonical outputs.
- [DONE] Modeling benchmark harness for logistic/tree baselines and feature ablations.
- [DONE] Calibrated gradient-boosted model family in the benchmark grid.
- [DONE] Typed explanation and manifest-declared uncertainty surfaces.
- [DONE] API contract v2 metadata for model provenance, explanation methods, uncertainty availability, and contextual geography.
- [DONE] Separate causal inference specification for smoking, physical activity, BMI, and alcohol.
- [DONE] Causal workbench prototype for sensitivity-tested, non-serving smoking-to-lung-disease estimates.
- [DONE] UI information architecture with Explorer, Data Evidence, Model Cards, and Scenario Lab pages.
- [DONE] Explorer UX upgrade for input deltas, accessible anatomy selection, explanation caveats, uncertainty copy, and color-blind-safe legends.
- [DONE] Deployment packaging for Render API/static frontend and Vercel static frontend handoff.
- [DONE] Public GitHub Release artifact download with SHA256 verification for Render artifact mode;
  production config points to context-aware `real-20260507-final`.
- [DONE] Geography serving foundation with explicit state-year context selection and readiness
  lookup.
- [DONE] Context-aware artifact training and serving activation for manifest-declared state-year
  ACS/SVI features, with county-level context kept inactive.
- [DONE] Context-aware artifact manifests record explicit ACS/SVI context vintage when
  `context_data_year` differs from the BRFSS label year.
- [DONE] Context transparency UX separates editable personal inputs from background state-year
  context across Explorer, Data Evidence, Model Cards, and Scenario Lab.

## Current baseline

### Core user workflow

- [DONE] UI loads metadata and default scenarios (`frontend/src/App.tsx`).
- [DONE] User edits current and what-if inputs side by side with live compare updates (`frontend/src/components/scenario-form.tsx`).
- [DONE] UI calls compare endpoint and renders results (`frontend/src/api/client.ts`).
- [DONE] Organ heatmap renders delta, baseline, and scenario views with callouts, keyboard-selectable overlays, and responsive layout coverage (`frontend/src/components/body-heatmap.tsx`).
- [DONE] Drill-down shows condition probabilities, drivers, citations, explanation caveats, uncertainty copy, and guidance (`frontend/src/components/condition-inspector.tsx`).
- [DONE] Backend exposes stable typed contract (`src/longevity_lab/api/schemas.py`).
- [DONE] Backend compares two scenarios through `POST /api/scenario/compare`, using artifact-backed scoring when a valid local bundle exists and labeled demo scoring otherwise (`src/longevity_lab/api/routes/scenario.py`).

### Data pipeline

- [DONE] Dataset directory layout and typed path builder (`src/longevity_lab/pipeline/ingest.py`).
- [DONE] BRFSS download script with provenance (`src/longevity_lab/pipeline/download_brfss.py`).
- [DONE] BRFSS decode and Parquet build for v2 scenario/editable, adjustment, label, and survey-weight columns (`src/longevity_lab/pipeline/build_brfss_tables.py`).
- [DONE] EPA AirData annual AQI, PM2.5, and ozone download and preprocessing (`src/longevity_lab/pipeline/download_epa_airdata.py`, `src/longevity_lab/pipeline/build_epa_tables.py`).
- [DONE] BRFSS/EPA/ACS/SVI state-year join with backwards-compatible `annual_aqi`, BRFSS v2 covariates, quality-gated pollutant features, and manifest-gated context features (`src/longevity_lab/pipeline/build_integrated_tables.py`).
- [DONE] Integrated person-year tables preserve BRFSS v2 covariates for default training (`src/longevity_lab/pipeline/build_integrated_tables.py`).
- [DONE] Expected EPA territory coverage gaps handled without breaking integrated builds (`src/longevity_lab/pipeline/build_integrated_tables.py`).
- [DONE] Small sample slice committed in `data/sample/` for dev/testing only.
- [DONE] DuckDB stable views builder (`src/longevity_lab/pipeline/build_duckdb_views.py`).
- [DONE] Pipeline CLIs default to repo-root `data/` even when invoked from subdirectories (`src/longevity_lab/pipeline/common.py`).
- [DONE] Source registry records official URLs, download templates, year support, expected files, checksum policy, license notes, and landing paths (`conf/data_sources.yaml`).
- [DONE] Optional source-screening registry, rubric, and Markdown CLI for later public data candidates without downloading raw data (`conf/data_source_candidates.yaml`, `src/longevity_lab/pipeline/source_screening.py`, `docs/data_source_candidate_screen.md`).
- [DONE] BRFSS and EPA download provenance embeds registry metadata (`src/longevity_lab/pipeline/provenance.py`).
- [DONE] ACS 5-year curated context downloader for state/county JSON with registry-backed provenance (`src/longevity_lab/pipeline/download_acs.py`).
- [DONE] CDC/ATSDR SVI U.S. county CSV downloader with registry-backed provenance (`src/longevity_lab/pipeline/download_svi.py`).
- [DONE] ACS/SVI county-year and state-year context tables with ACS MOE availability flags (`src/longevity_lab/pipeline/build_context_tables.py`, `conf/context_features.yaml`).
- [DONE] CDC PLACES county Open Data downloader with registry-backed provenance (`src/longevity_lab/pipeline/download_places.py`).
- [DONE] PLACES county-year contextual tables for matching modeled conditions where PLACES has a public measure (heart disease, COPD, asthma, stroke, depression, diabetes, arthritis) plus smoking, binge drinking, physical inactivity, obesity, and short sleep (`src/longevity_lab/pipeline/build_places_tables.py`).
- [DONE] External PLACES reasonableness report compares aggregate model risk patterns with PLACES modeled estimates while documenting that PLACES is not an independent person-level label source (`src/longevity_lab/pipeline/validate_external_context.py`).

### Modeling

- [DONE] Hydra-based training entrypoint (`src/longevity_lab/pipeline/train.py`, `conf/train.yaml`).
- [DEMO] Demo risk engine remains available as explicit or fallback scoring (`src/longevity_lab/services/scenario_service.py`).
- [DONE] Decision-tree baseline per condition with Optuna tuning (`src/longevity_lab/pipeline/modeling.py`).
- [DONE] Calibration for probability outputs (`src/longevity_lab/pipeline/modeling.py`).
- [DONE] Evaluation script and metrics report scaffold (`src/longevity_lab/pipeline/evaluate.py`).
- [DONE] Subgroup/slice analysis export for trained bundles (`src/longevity_lab/pipeline/evaluate.py`, `src/longevity_lab/pipeline/modeling.py`).
- [DONE] Reproducible benchmark harness writes metrics, calibration curves, subgroup metrics, and model-card-ready manifests (`src/longevity_lab/pipeline/benchmarks.py`, `conf/benchmark.yaml`).
- [DONE] Benchmark harness compares calibrated histogram gradient boosting and optional XGBoost candidates against the decision-tree baseline, recording skipped XGBoost rows when the optional dependency is unavailable (`src/longevity_lab/pipeline/benchmarks.py`, `conf/model/hist_gradient_boosting.yaml`, `conf/model/xgboost.yaml`).
- [DONE] Training config separates scenario-editable features from BRFSS adjustment covariates and state-year ACS/SVI context features, applying survey weights plus condition-specific leakage exclusions (`conf/train.yaml`, `src/longevity_lab/pipeline/modeling.py`).
- [DONE] Active training scope covers eight BRFSS-derived conditions: heart disease, chronic lung disease, asthma, stroke, depression, diabetes, chronic kidney disease, and arthritis (`conf/train.yaml`, `src/longevity_lab/domain/catalog.py`).
- [DONE] Artifact manifest schema, bundle loader, context lookup provenance, and safe auto-detection (`src/longevity_lab/artifacts/manifest.py`, `src/longevity_lab/artifacts/store.py`).
- [DONE] Explanation outputs aligned to saved explanation trees, manifest-declared compact SHAP
  artifacts for supported tree ensembles, and manifest-declared uncertainty intervals
  (`src/longevity_lab/services/artifact_engine.py`,
  `src/longevity_lab/services/explanations.py`, `src/longevity_lab/services/uncertainty.py`).
- [DONE] Training packages held-out empirical calibration-interval payloads per condition and
  surfaces uncertainty diagnostics in scenario responses and model cards
  (`src/longevity_lab/pipeline/modeling.py`, `src/longevity_lab/services/model_card_service.py`).

### Causal inference

- [DONE] Spec-only causal questions documented for smoking, physical activity, BMI, and alcohol (`docs/causal_inference.md`).
- [DONE] Machine-readable causal question registry with populations, treatments, outcomes, estimands, confounders, exclusions, DAG assumptions, negative controls, and sensitivity checks (`conf/causal/questions.yaml`).
- [DONE] Predictive risk and causal estimates are documented as separate surfaces; Explorer scenario deltas must not be described as causal effects.
- [DONE] Non-serving smoking-to-chronic-lung-disease workbench prepares an analysis table, records DAG assumptions, runs overlap/balance diagnostics, estimates a weighted logistic g-computation risk difference, runs local refutations, and writes JSON/Markdown reports under gitignored `data/processed/reports/causal/` (`src/longevity_lab/causal/`, `conf/causal/smoking_lung.yaml`).
- [DONE] Causal workbench coverage extends to physical activity-to-diabetes, BMI-to-diabetes, and alcohol-to-depression audit reports, with non-serving subgroup and optional heterogeneous-effect report sections.

### Backend/API

- [DONE] Health check (`GET /api/health`) (`src/longevity_lab/api/routes/health.py`).
- [DONE] Metadata bootstrap with runtime mode/artifact status (`GET /api/metadata/bootstrap`) (`src/longevity_lab/api/routes/metadata.py`).
- [DONE] Pipeline status endpoint (`GET /api/pipeline/status`) (`src/longevity_lab/api/routes/pipeline.py`).
- [DONE] Model-card endpoint exposes active artifact metrics (`GET /api/models/cards`) (`src/longevity_lab/api/routes/models.py`).
- [DONE] Evidence endpoint exposes source registry roles, asset readiness, production artifact download status, active-vs-available features, reports, and inactive gaps (`GET /api/evidence/status`) (`src/longevity_lab/api/routes/evidence.py`).
- [DONE] Geography context endpoint exposes state-year options and active artifact/local context readiness without absolute local paths (`GET /api/context/geographies`) (`src/longevity_lab/api/routes/context.py`).
- [DONE] Service layer and engine abstraction (`src/longevity_lab/services/scenario_service.py`).
- [DONE] Artifact-backed engine path (`src/longevity_lab/services/artifact_engine.py`).
- [DONE] Versioned v2 response metadata shares active model mode, artifact id, data vintage, explanation methods, uncertainty availability, and inferred contextual geography across bootstrap and scenario compare responses (`src/longevity_lab/services/contract_metadata.py`).
- [DONE] Input validation and safe defaults for missing features.
- [DONE] Structured logging and request IDs.

### Frontend UX

- [DONE] Body map uses a reference-based silhouette underlay plus SVG organ overlays for heart, lungs, brain, pancreas, kidneys, and joints.
- [DONE] Explorer layout includes side-by-side current and what-if inputs, a persistent comparison strip, and absolute-risk versus relative-change legends.
- [DONE] Scenario editing is live and updates the evaluation snapshot automatically.
- [DONE] High-risk drill-down panels surface public-health guidance links when either current or what-if profile is in the red band.
- [DONE] Explorer view shows a compact non-diagnostic disclaimer and runtime scoring-mode banner.
- [DONE] Explorer keeps state-year geography context separate from lifestyle scenario inputs and labels it as background context.
- [DONE] Explorer shows selected state/year, lookup readiness, context feature count, model
  active/inactive status, context vintage, and caveats in a dedicated context card.
- [DONE] Named product pages separate the Explorer, data evidence, active model-card metadata, and scenario summary workflows (`frontend/src/pages/`).
- [DONE] Better "what changed" deltas per organ/condition through visible changed-input chips and drill-down delta summaries.
- [DONE] Basic accessibility pass for keyboard-selectable anatomy overlays and text-supported color legends.
- [DONE] Mobile/responsive layout pass.
- [DONE] Data Evidence, Model Cards, and Scenario Lab group active state-year context, inactive
  county context, validation-only PLACES, context ablation lift, subgroup caveats, and
  geography/context summary rows separately from lifestyle inputs.

### Reproducibility

- [DONE] Backend tests (`tests/`).
- [DONE] Python type-check and lint configured (`pyproject.toml`).
- [DONE] Scripted processed-data EDA report writes JSON summaries, SVG/PNG figures, Markdown, and HTML under gitignored `reports/` (`src/longevity_lab/reports/eda.py`, `docs/reports.md`).
- [DONE] Frontend lint/type/build configured (`frontend/`).
- [DONE] CI workflow (`.github/workflows/ci.yml`).
- [DONE] One-command dev checks (`scripts/check_all.ps1`, `scripts/check_all.sh`).
- [DONE] E2E smoke tests (`frontend/e2e/`).
- [DONE] Free-tier deployment profile documented with Render Blueprint config and Vite API-origin support (`render.yaml`, `docs/deployment.md`, `frontend/vite.config.ts`, `frontend/.env.example`).
- [DONE] Build-time model artifact downloader verifies public release bundles before production artifact mode (`scripts/download_model_bundle.py`).
- [DONE] One-command dev bootstrap for Windows and macOS (`scripts/bootstrap_dev.ps1`, `scripts/bootstrap_dev.sh`).
- [DONE] Artifact-backed runtime no longer requires Optuna just to load packaged bundles (`src/longevity_lab/pipeline/modeling.py`).
- [DONE] Dataset sources and provenance docs (`docs/datasets.md`, `docs/data_dictionary.md`).
- [DONE] Finalize ethics and health disclaimer language across the UI and documentation through shared frontend copy, E2E assertions, and docs interpretation limits.

## Highest-ROI next tasks

Detailed PR scopes and Codex prompts are in `docs/superpowers/plans/2026-05-06-remaining-work-pr-roadmap.md`.

1. Extend typed explanation and uncertainty coverage as new artifact families are trained.
2. Train and promote newer artifact families when their benchmark evidence justifies activation.
