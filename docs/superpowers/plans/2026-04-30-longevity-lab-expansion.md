# Longevity Lab Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand Longevity Lab from a baseline prototype into a reproducible, public-data-backed risk communication platform with stronger data, modeling, evaluation, causal-analysis, and UI surfaces.

**Architecture:** Keep the existing plain monorepo. Add data-source adapters, provenance-first feature tables, calibrated model registries, separate causal-analysis scripts, and versioned API/UI contracts without bundling raw datasets or model artifacts.

**Tech Stack:** Python 3.12, PDM, pandas, pyarrow, DuckDB, scikit-learn, optional XGBoost/LightGBM/EconML/DoWhy/MAPIE extras, FastAPI, Pydantic, React, TypeScript, Vite, Playwright.

---

## Execution Rules

- Create a worktree per PR under `.worktrees/<branch-slug>` after confirming `.worktrees/` is ignored.
- Use branch names such as `codex/pr-02-data-source-registry`.
- Keep each PR independently reviewable and open a GitHub pull request before merging.
- Use a fresh implementation subagent for each PR and a fresh reviewer subagent for adversarial review.
- Do not merge until local review reports no new P0, P1, or P2 issues against the latest commit hash.
- Update `docs/feature_status.md`, `docs/roadmap.md`, schema docs, and quickstart docs whenever the PR changes workflow, data, contracts, or user-visible behavior.
- Do not commit `data/external/`, `data/processed/`, `artifacts/models/`, `.codex/`, `.worktrees/`, or local `AGENTS.md`.

## PR Prompt Template

Use this template for every implementation PR:

```text
You are implementing PR <number>: <title> in the Longevity Lab repo.

Read first:
- AGENTS.md
- docs/roadmap.md
- docs/superpowers/plans/2026-04-30-longevity-lab-expansion.md
- docs/feature_status.md
- docs/schema_contracts.md
- docs/data_dictionary.md

Scope:
- Implement only the PR scope listed in the plan.
- Keep all changed docs/tests/contracts synchronized.
- Do not touch unrelated feature areas.

Validation:
- Run the narrowest relevant checks named in the PR prompt.
- Run broader checks only after targeted checks pass.
- Report any skipped checks with exact reason.

Ready-to-merge gate:
- Open a GitHub pull request.
- Run local adversarial review against the latest commit hash.
- Address all new P0/P1/P2 issues before marking the PR ready.
```

## PR 00: Governance, Overlay, and Roadmap

**Branch:** `codex/pr-00-governance-roadmap`

**Purpose:** Establish the product roadmap, local overlay, worktree policy, and drift-sensitive documentation before feature implementation begins.

**Files:**
- Modify: `.gitignore`
- Create or update locally: `.codex/README.md`, `.codex/config.toml`, `.codex/runbooks/*.md`, `AGENTS.md`
- Create: `docs/roadmap.md`
- Create: `docs/superpowers/plans/2026-04-30-longevity-lab-expansion.md`
- Modify: `README.md`, `docs/feature_status.md`, `docs/implementation_plan.md`

**Implementation prompt:**
```text
Finish PR 00 by syncing the repository documentation and local Codex overlay with the independent product roadmap. Keep AGENTS.md and .codex local-only because the current .gitignore intentionally excludes them. Add .worktrees/ to .gitignore. Do not implement product features.
```

**Checks:**
- `git diff --check`
- `python - <<'PY'\nimport pathlib, tomllib\nfor path in pathlib.Path('.codex').rglob('*.toml'):\n    tomllib.loads(path.read_text())\nprint('overlay toml ok')\nPY`
- Manual scan for stale legacy roadmap language in `README.md`, `docs/feature_status.md`, and `docs/implementation_plan.md`.

## PR 01: Artifact-First Runtime

**Branch:** `codex/pr-01-artifact-first-runtime`

**Purpose:** Make the backend prefer a valid local artifact bundle and label demo mode as fallback-only.

**Files:**
- Modify: `src/longevity_lab/api/main.py`
- Modify: `src/longevity_lab/services/scenario_service.py`
- Modify: `src/longevity_lab/artifacts/store.py`
- Modify: `src/longevity_lab/api/schemas.py`
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/components/condition-inspector.tsx`
- Test: `tests/test_api.py`, `tests/test_artifact_store.py`, `tests/test_scenario_service.py`, `frontend/e2e/app.spec.ts`
- Docs: `README.md`, `.env.example`, `docs/quickstart.md`, `docs/feature_status.md`

**Implementation prompt:**
```text
Implement artifact-first serving. At startup, if LONGEVITY_LAB_ENGINE is unset and a valid local artifact bundle exists, use ArtifactScenarioEngine. If no valid bundle exists, use DemoScenarioEngine and include metadata that clearly says demo mode is active. Preserve explicit LONGEVITY_LAB_ENGINE overrides. Add tests for auto-detect, explicit artifact, explicit demo, invalid bundle fallback, and metadata propagation to the frontend.
```

**Checks:**
- `pdm run pytest tests/test_api.py tests/test_artifact_store.py tests/test_scenario_service.py`
- `pdm run ruff check src tests`
- `cd frontend; npm run check`
- `cd frontend; npm run test:e2e`

## PR 02: Data Source Registry

**Branch:** `codex/pr-02-data-source-registry`

**Purpose:** Create a central registry for public data sources, downloader metadata, checksums, retrieval dates, and license/terms notes.

**Files:**
- Create: `src/longevity_lab/pipeline/sources.py`
- Create: `src/longevity_lab/pipeline/provenance.py`
- Create: `conf/data_sources.yaml`
- Modify: `src/longevity_lab/pipeline/download_brfss.py`
- Modify: `src/longevity_lab/pipeline/download_epa_airdata.py`
- Test: `tests/test_data_sources.py`, `tests/test_pipeline_common.py`
- Docs: `docs/datasets.md`, `docs/data_dictionary.md`, `docs/feature_status.md`

**Implementation prompt:**
```text
Add a versioned data-source registry that records source_id, title, official_url, download_url_template, year_support, geography, expected_file_pattern, checksum_policy, license_note, and local landing path. Refactor BRFSS and EPA downloaders to write registry-backed provenance JSON without changing existing CLI behavior.
```

**Checks:**
- `pdm run pytest tests/test_data_sources.py tests/test_pipeline_common.py tests/test_download_brfss.py tests/test_epa_tables_cli.py`
- `pdm run ruff check src tests`
- `pdm run mypy src tests`

## PR 03: BRFSS v2 Feature Contract

**Branch:** `codex/pr-03-brfss-v2-features`

**Purpose:** Expand BRFSS feature coverage while preserving a clear user-input subset.

**Files:**
- Modify: `src/longevity_lab/pipeline/build_brfss_tables.py`
- Modify: `src/longevity_lab/pipeline/modeling.py`
- Modify: `src/longevity_lab/api/schemas.py`
- Modify: `conf/train.yaml`
- Test: `tests/test_brfss_decode.py`, `tests/test_training_pipeline.py`, `tests/test_api.py`
- Docs: `docs/data_dictionary.md`, `docs/schema_contracts.md`, `docs/feature_status.md`

**Implementation prompt:**
```text
Add a BRFSS v2 feature contract that separates scenario-editable inputs from adjustment/context covariates. Include survey weights, sex, race/ethnicity where available, healthcare access, sleep if a supported year contains it, and physical/mental health days where label leakage is avoided. Document each variable mapping and exclusion reason.
```

**Checks:**
- `pdm run pytest tests/test_brfss_decode.py tests/test_training_pipeline.py tests/test_api.py`
- `pdm run ruff check src tests`
- `pdm run mypy src tests`

## PR 04: EPA Pollutant Expansion

**Branch:** `codex/pr-04-epa-pollutant-expansion`

**Purpose:** Replace annual AQI-only environmental context with pollutant-specific features and quality flags.

**Files:**
- Modify: `src/longevity_lab/pipeline/download_epa_airdata.py`
- Modify: `src/longevity_lab/pipeline/build_epa_tables.py`
- Modify: `src/longevity_lab/pipeline/build_integrated_tables.py`
- Test: `tests/test_epa_tables.py`, `tests/test_epa_tables_cli.py`, `tests/test_integration_join.py`
- Docs: `docs/datasets.md`, `docs/data_dictionary.md`, `docs/feature_status.md`

**Implementation prompt:**
```text
Add scriptable EPA annual summaries for PM2.5, ozone, and AQI. Persist county-year and state-year aggregates with monitor-count and observation-completeness flags. Keep the existing annual_aqi field for backwards compatibility and add pollutant features only after data-quality checks pass.
```

**Checks:**
- `pdm run pytest tests/test_epa_tables.py tests/test_epa_tables_cli.py tests/test_integration_join.py`
- `pdm run ruff check src tests`
- `pdm run mypy src tests`

## PR 05: ACS and SVI Context Features

**Branch:** `codex/pr-05-acs-svi-context`

**Purpose:** Add curated socioeconomic and social-vulnerability context features.

**Files:**
- Create: `src/longevity_lab/pipeline/download_acs.py`
- Create: `src/longevity_lab/pipeline/download_svi.py`
- Create: `src/longevity_lab/pipeline/build_context_tables.py`
- Create: `conf/context_features.yaml`
- Test: `tests/test_context_tables.py`
- Docs: `docs/datasets.md`, `docs/data_dictionary.md`, `docs/feature_status.md`

**Implementation prompt:**
```text
Implement ACS 5-year and CDC/ATSDR SVI downloads with a small curated feature set: poverty, income, education, insurance, disability, broadband, SVI overall, and SVI themes. Build state-year and county-year context tables. Record ACS margins-of-error availability and keep context fields separate from scenario-editable inputs.
```

**Checks:**
- `pdm run pytest tests/test_context_tables.py tests/test_pipeline_common.py`
- `pdm run ruff check src tests`
- `pdm run mypy src tests`

## PR 06: PLACES Context and External Validation

**Branch:** `codex/pr-06-places-validation`

**Purpose:** Add CDC PLACES as contextual geography and external reasonableness checks.

**Files:**
- Create: `src/longevity_lab/pipeline/download_places.py`
- Create: `src/longevity_lab/pipeline/build_places_tables.py`
- Create: `src/longevity_lab/pipeline/validate_external_context.py`
- Test: `tests/test_places_tables.py`, `tests/test_external_context_validation.py`
- Docs: `docs/datasets.md`, `docs/data_dictionary.md`, `docs/feature_status.md`

**Implementation prompt:**
```text
Ingest CDC PLACES county-level measures for the five modeled conditions and relevant behaviors. Build contextual tables and an external reasonableness report comparing model aggregate risk patterns with PLACES estimates. Explicitly document that PLACES derives from modeled estimates and is not an independent person-level label source.
```

**Checks:**
- `pdm run pytest tests/test_places_tables.py tests/test_external_context_validation.py`
- `pdm run ruff check src tests`
- `pdm run mypy src tests`

## PR 07: Scripted EDA Reports

**Branch:** `codex/pr-07-scripted-eda-reports`

**Purpose:** Replace notebooks as source-of-truth with reproducible report scripts.

**Files:**
- Create: `src/longevity_lab/reports/eda.py`
- Create: `src/longevity_lab/reports/figures.py`
- Create: `conf/reports/eda.yaml`
- Create: `docs/reports.md`
- Test: `tests/test_reports_eda.py`
- Docs: `README.md`, `docs/feature_status.md`

**Implementation prompt:**
```text
Create a scripted EDA report command that reads processed tables and writes JSON summaries, PNG/SVG figures, and Markdown/HTML report outputs under a gitignored reports directory. Preserve notebooks only as optional exploration artifacts, not canonical evidence.
```

**Checks:**
- `pdm run pytest tests/test_reports_eda.py`
- `pdm run ruff check src tests`
- `pdm run mypy src tests`

## PR 08: Modeling Benchmark Harness

**Branch:** `codex/pr-08-modeling-benchmark-harness`

**Purpose:** Make model comparison reproducible across baselines, data ablations, and subgroups.

**Files:**
- Create: `src/longevity_lab/pipeline/benchmarks.py`
- Create: `conf/benchmark.yaml`
- Modify: `src/longevity_lab/pipeline/modeling.py`
- Test: `tests/test_benchmarks.py`, `tests/test_training_pipeline.py`
- Docs: `docs/modeling.md`, `docs/feature_status.md`

**Implementation prompt:**
```text
Build a benchmark harness that trains logistic baseline, decision tree baseline, and ablation variants under identical splits. Persist metrics, calibration curves, subgroup metrics, feature lists, and model-card-ready manifests. Do not introduce external GBDT dependencies in this PR.
```

**Checks:**
- `pdm run pytest tests/test_benchmarks.py tests/test_training_pipeline.py`
- `pdm run ruff check src tests`
- `pdm run mypy src tests`

## PR 09: Calibrated Gradient-Boosted Models

**Branch:** `codex/pr-09-calibrated-gbdt-models`

**Purpose:** Add contemporary tabular models while preserving calibrated probabilities and interpretable baselines.

**Files:**
- Modify: `pyproject.toml`
- Create: `conf/model/hist_gradient_boosting.yaml`
- Create: `conf/model/xgboost.yaml`
- Modify: `src/longevity_lab/pipeline/modeling.py`
- Test: `tests/test_training_pipeline.py`, `tests/test_benchmarks.py`
- Docs: `docs/modeling.md`, `docs/feature_status.md`

**Implementation prompt:**
```text
Add calibrated HistGradientBoostingClassifier and optional XGBoost model families to the benchmark harness. Keep dependencies optional where possible. Support class imbalance handling, monotonic constraints when configured, calibration, and per-condition artifact manifests. Compare all models against the decision-tree baseline.
```

**Checks:**
- `pdm install -G dev -G train`
- `pdm run pytest tests/test_training_pipeline.py tests/test_benchmarks.py`
- `pdm run ruff check src tests`
- `pdm run mypy src tests`

## PR 10: Explainability and Uncertainty

**Branch:** `codex/pr-10-explainability-uncertainty`

**Purpose:** Add typed explanations and uncertainty summaries that match each model family.

**Files:**
- Modify: `src/longevity_lab/api/schemas.py`
- Modify: `src/longevity_lab/services/artifact_engine.py`
- Create: `src/longevity_lab/services/explanations.py`
- Create: `src/longevity_lab/services/uncertainty.py`
- Modify: `frontend/src/types.ts`
- Test: `tests/test_artifact_engine.py`, `tests/test_api.py`
- Docs: `docs/schema_contracts.md`, `docs/modeling.md`, `docs/feature_status.md`

**Implementation prompt:**
```text
Introduce typed explanation records with fields for feature, display_name, direction, magnitude, method, and caveat. Preserve tree-path explanations for decision trees and add SHAP-backed explanations for supported tree ensembles. Add calibrated uncertainty fields only when the artifact manifest declares them available.
```

**Checks:**
- `pdm run pytest tests/test_artifact_engine.py tests/test_api.py`
- `pdm run ruff check src tests`
- `pdm run mypy src tests`
- `cd frontend; npm run check`

## PR 11: Causal Inference Specification

**Branch:** `codex/pr-11-causal-inference-spec`

**Purpose:** Define causal questions and assumptions before any causal code is served.

**Files:**
- Create: `docs/causal_inference.md`
- Create: `conf/causal/questions.yaml`
- Modify: `docs/roadmap.md`
- Modify: `docs/feature_status.md`

**Implementation prompt:**
```text
Create a causal inference spec for smoking, physical activity, BMI, and alcohol as separate treatment questions. For each question, define population, treatment, outcome, estimand, candidate confounders, excluded variables, DAG assumptions, negative controls, sensitivity checks, and why results must be presented separately from predictive risk.
```

**Checks:**
- `git diff --check`
- Manual review against `docs/roadmap.md` product boundary and causal workflow.

## PR 12: Causal Workbench Prototype

**Branch:** `codex/pr-12-causal-workbench`

**Purpose:** Add non-serving causal-analysis scripts for assumption-tested exploratory estimates.

**Files:**
- Create: `src/longevity_lab/causal/datasets.py`
- Create: `src/longevity_lab/causal/estimators.py`
- Create: `src/longevity_lab/causal/reports.py`
- Create: `conf/causal/smoking_lung.yaml`
- Test: `tests/test_causal_datasets.py`, `tests/test_causal_reports.py`
- Docs: `docs/causal_inference.md`, `docs/feature_status.md`

**Implementation prompt:**
```text
Implement a causal workbench for one fully specified question from PR 11. The script should prepare analysis data, run adjustment diagnostics, estimate an association/effect under stated assumptions, run sensitivity/refutation checks, and write a report. Do not expose causal results through the API or UI in this PR.
```

**Checks:**
- `pdm run pytest tests/test_causal_datasets.py tests/test_causal_reports.py`
- `pdm run ruff check src tests`
- `pdm run mypy src tests`

## PR 13: API Contract v2

**Branch:** `codex/pr-13-api-contract-v2`

**Purpose:** Version the API contracts for richer context, uncertainty, explanation methods, and model metadata.

**Files:**
- Modify: `src/longevity_lab/api/schemas.py`
- Modify: `src/longevity_lab/api/routes/metadata.py`
- Modify: `src/longevity_lab/api/routes/scenario.py`
- Modify: `frontend/src/types.ts`
- Test: `tests/test_api.py`, `tests/test_pipeline_status_api.py`, `frontend/e2e/app.spec.ts`
- Docs: `docs/schema_contracts.md`, `docs/feature_status.md`

**Implementation prompt:**
```text
Add explicit API contract versioning and backwards-compatible v1-to-v2 response fields for model mode, artifact ID, data vintage, explanation method, uncertainty availability, and contextual geography. Keep routes thin and domain logic in services.
```

**Checks:**
- `pdm run pytest tests/test_api.py tests/test_pipeline_status_api.py`
- `pdm run ruff check src tests`
- `pdm run mypy src tests`
- `cd frontend; npm run check`
- `cd frontend; npm run test:e2e`

## PR 14: UI Information Architecture

**Branch:** `codex/pr-14-ui-information-architecture`

**Purpose:** Add product pages for Explorer, Data Evidence, Model Cards, and Scenario Lab.

**Files:**
- Modify: `frontend/src/App.tsx`
- Create: `frontend/src/pages/ExplorerPage.tsx`
- Create: `frontend/src/pages/DataEvidencePage.tsx`
- Create: `frontend/src/pages/ModelCardsPage.tsx`
- Create: `frontend/src/pages/ScenarioLabPage.tsx`
- Modify: `frontend/src/styles.css`
- Test: `frontend/e2e/app.spec.ts`
- Docs: `docs/feature_status.md`

**Implementation prompt:**
```text
Refactor the frontend into named pages with clear navigation while preserving the existing Explorer behavior. Add non-stub Data Evidence, Model Cards, and Scenario Lab pages that render real metadata from existing endpoints where available and honest unavailable states where not.
```

**Checks:**
- `cd frontend; npm run check`
- `cd frontend; npm run lint`
- `cd frontend; npm run build`
- `cd frontend; npm run test:e2e`

## PR 15: Explorer UX Upgrade

**Branch:** `codex/pr-15-explorer-ux-upgrade`

**Purpose:** Improve scenario sensitivity, anatomy interaction, accessibility, and health-literacy copy.

**Files:**
- Modify: `frontend/src/components/body-heatmap.tsx`
- Modify: `frontend/src/components/condition-inspector.tsx`
- Modify: `frontend/src/components/scenario-form.tsx`
- Modify: `frontend/src/styles.css`
- Modify: `frontend/src/domain/health-recommendations.ts`
- Test: `frontend/e2e/app.spec.ts`
- Docs: `docs/feature_status.md`

**Implementation prompt:**
```text
Upgrade Explorer interactions so organ and condition deltas are easier to understand. Add keyboard-accessible anatomy selection, clearer uncertainty and explanation caveats, visible current/what-if input differences, color-blind-safe text-supported legends, and plain-language high-risk guidance. Do not add new medical advice.
```

**Checks:**
- `cd frontend; npm run check`
- `cd frontend; npm run lint`
- `cd frontend; npm run build`
- `cd frontend; npm run test:e2e`

## PR 16: Deployment Packaging

**Branch:** `codex/pr-16-deployment-packaging`

**Purpose:** Create a realistic free-tier deployment path without shipping raw data or full artifacts.

**Files:**
- Create: `docs/deployment.md`
- Create: `render.yaml`
- Modify: `frontend/vite.config.ts`
- Modify: `.env.example`
- Modify: `README.md`
- Test: `scripts/check_all.ps1`, `scripts/check_all.sh`
- Docs: `docs/feature_status.md`

**Implementation prompt:**
```text
Document and configure a free-tier deployment profile. Use Vercel for static frontend or Render for a small FastAPI deployment only if the config is explicit and non-secret. Include sample-artifact/demo modes, cold-start caveats, artifact retrieval strategy, and local-first instructions. Do not commit generated artifacts.
```

**Checks:**
- `pdm run pytest`
- `cd frontend; npm run build`
- `git diff --check`

## Parallelization Map

- PR 01 can run after PR 00.
- PRs 02, 11, and 14 can run in parallel after PR 00 because their write surfaces are mostly separate.
- PRs 03, 04, and 05 depend on PR 02 and can run in parallel if their schema changes are coordinated through `docs/data_dictionary.md`.
- PR 06 depends on PR 02 and preferably PR 05.
- PR 07 depends on the data-table PRs that define the report inputs.
- PRs 08 and 09 are sequential because 09 extends the benchmark harness.
- PR 10 depends on PR 09 and must not race with PR 13 because both change API schemas.
- PR 12 depends on PR 11.
- PR 15 depends on PR 14 and benefits from PR 13.
- PR 16 should wait until the API/UI contracts stabilize.

## Review Checklist

- [ ] The PR touches only its declared files or explains why the touch set expanded.
- [ ] Data downloads are scriptable and write provenance.
- [ ] Model outputs include calibration and subgroup evidence when relevant.
- [ ] Explanations match the method used by the artifact.
- [ ] UI copy remains non-diagnostic and plain-language.
- [ ] Docs, tests, schema contracts, and feature status are synchronized.
- [ ] Local adversarial review reports no new P0, P1, or P2 findings for the latest hash.
