# Active Evidence and Model Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the deployed product accurately show implemented data/model evidence, promote a refreshed artifact using pollutant features, and add only new BRFSS conditions/organs that are directly supported by current public labels.

**Architecture:** Add an additive evidence-status API and UI while preserving existing pipeline/model-card endpoints. Expand BRFSS labels and the static organ/condition catalog for asthma, chronic kidney disease, and arthritis; keep ACS/SVI/PLACES visible as available/context evidence unless geography-aware inference is implemented later. Retrain and publish a new artifact bundle outside git.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, pandas, scikit-learn, joblib, React, TypeScript, Vite, Playwright, GitHub Releases, Render.

---

## Scope Decisions

- Add active model features `pm25_mean` and `ozone_mean` because they are already quality-gated in the integrated table and can be safely surfaced as scenario-editable environmental inputs.
- Do not activate ACS/SVI in scoring in this PR because serving would need a geography input plus artifact-bundled state context lookup; show it as implemented but inactive context evidence.
- Do not train on PLACES because it is modeled aggregate validation/context, not person-level labels.
- Add three direct BRFSS label families: asthma, chronic kidney disease, and arthritis. These add one existing organ group (lungs) plus two new organs/regions (kidneys and joints).
- Keep the UI non-diagnostic; new guidance remains public-health literacy copy with CDC citations.

## Tasks

### Task 1: Evidence Status API

**Files:**
- Modify: `src/longevity_lab/api/schemas.py`
- Create: `src/longevity_lab/api/routes/evidence.py`
- Create: `src/longevity_lab/services/evidence_service.py`
- Modify: `src/longevity_lab/api/main.py`
- Test: `tests/test_evidence_status_api.py`

- [ ] Add schema types for source registry summaries, grouped local assets, production artifact status, feature inventory, report evidence, and inactive gaps.
- [ ] Implement `EvidenceService` that reads `conf/data_sources.yaml`, pipeline paths, provenance files, report directories, active artifact manifests, and training config.
- [ ] Add `GET /api/evidence/status?year=2023` as an additive route.
- [ ] Test that the endpoint exposes all implemented source families, never leaks absolute paths or release URLs, and distinguishes active model features from available inactive features.

### Task 2: BRFSS Conditions and Catalog

**Files:**
- Modify: `src/longevity_lab/pipeline/build_brfss_tables.py`
- Modify: `src/longevity_lab/pipeline/build_integrated_tables.py`
- Modify: `src/longevity_lab/domain/catalog.py`
- Modify: `frontend/src/content/health-recommendations.ts`
- Test: `tests/test_brfss_decode.py`, `tests/test_integration_join.py`, `tests/test_api.py`
- Docs: `docs/data_dictionary.md`, `docs/schema_contracts.md`, `docs/feature_status.md`

- [ ] Decode `label_asthma` from `ASTHMA3` + `ASTHNOW`, `label_kidney_disease` from `CHCKDNY2`, and `label_arthritis` from `HAVARTH4`.
- [ ] Carry the new labels into `integrated_person_year`.
- [ ] Add catalog entries for asthma, chronic kidney disease, and arthritis, plus kidneys and joints organ metadata.
- [ ] Add CDC-backed high-risk guidance copy for the three new conditions.
- [ ] Test decoding, integration, bootstrap metadata, and scenario output compatibility.

### Task 3: Active Pollutant Feature Contract

**Files:**
- Modify: `src/longevity_lab/api/schemas.py`
- Modify: `src/longevity_lab/services/metadata_service.py`
- Modify: `src/longevity_lab/services/artifact_engine.py`
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/state/scenario-context.tsx`
- Modify: `frontend/src/components/scenario-form.tsx`
- Modify: `conf/train.yaml`, `conf/benchmark.yaml`
- Test: `tests/test_api.py`, `tests/test_training_pipeline.py`, `tests/test_benchmarks.py`

- [ ] Add `pm25_mean` and `ozone_mean` as bounded scenario-editable environmental inputs.
- [ ] Keep `annual_aqi` for backwards compatibility and ablation continuity.
- [ ] Add pollutant features to default training and benchmark configs with monotonic constraints.
- [ ] Ensure artifact inference receives pollutant values from the profile instead of median-only defaults.
- [ ] Test metadata bootstrap, profile validation, training manifests, and feature preprocessing.

### Task 4: Evidence and Explorer UI

**Files:**
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/pages/DataEvidencePage.tsx`
- Modify: `frontend/src/pages/ModelCardsPage.tsx`
- Modify: `frontend/src/pages/ScenarioLabPage.tsx`
- Modify: `frontend/src/components/body-heatmap.tsx`
- Modify: `frontend/src/components/condition-inspector.tsx`
- Modify: `frontend/src/styles.css`
- Test: `frontend/e2e/app.spec.ts`

- [ ] Replace the legacy-only Data Evidence view with source registry, local assets, production artifact, reports, feature inventory, and known gaps.
- [ ] Add model-card active-vs-available feature coverage.
- [ ] Add compact Explorer copy explaining editable inputs versus defaulted non-editable covariates.
- [ ] Draw supported kidney and joints overlays/callouts.
- [ ] Test the new UI sections and new condition/organ navigation.

### Task 5: Documentation and Deployment Config

**Files:**
- Modify: `README.md`
- Modify: `.env.example`
- Modify: `docs/deployment.md`
- Modify: `docs/modeling.md`
- Modify: `docs/data_dictionary.md`
- Modify: `docs/schema_contracts.md`
- Modify: `docs/feature_status.md`
- Modify: `render.yaml` after the new release artifact is published.

- [ ] Document what is active in scoring versus implemented only as context/evidence.
- [ ] Document the new condition labels and environmental inputs.
- [ ] Update deployment artifact id, release URL, and SHA after packaging.

### Task 6: Train, Package, Validate, Review, PR

**Generated outputs stay uncommitted:** `data/external/`, `data/processed/`, `artifacts/models/`, `reports/`.

- [ ] Run the full pipeline using existing local raw data or downloads.
- [ ] Train bundle `real-20260504-full` with `data.use_sample_if_missing=false`.
- [ ] Evaluate, package a POSIX-path zip, publish to GitHub Releases, update checksum references.
- [ ] Run targeted tests, full backend/frontend checks, Playwright E2E, local artifact download smoke, Render blueprint validation, and production smoke after merge/deploy.
- [ ] Run local adversarial review against `origin/main..HEAD` until no open P0/P1/P2 issues remain.
- [ ] Push branch, open PR, wait for CI, merge, clean up worktree/branch.
