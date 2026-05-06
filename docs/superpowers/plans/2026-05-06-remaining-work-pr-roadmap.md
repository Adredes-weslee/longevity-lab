# Remaining Work PR Roadmap

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert the remaining documented roadmap gaps into reviewable PRs with clear scope, dependencies, acceptance criteria, and Codex prompts.

**Architecture:** Keep geography-aware prediction, causal analysis, model explanation/uncertainty, responsive UI, ethics copy, and optional data-source research as separate tracks. Do not silently activate contextual or causal signals in the Explorer until the serving contract, artifact manifest, and user-facing caveats make the semantics explicit.

**Tech Stack:** Python 3.12, PDM, pandas, pyarrow, DuckDB, scikit-learn, optional SHAP/MAPIE/XGBoost extras, FastAPI, Pydantic, React, TypeScript, Vite, Playwright, GitHub Releases, Render.

---

## Execution Rules

- Create one branch per PR using `codex/pr-<number>-<slug>`.
- Use worktrees under `.worktrees/<branch-slug>` when two PRs can run independently.
- Do not commit `data/external/`, `data/processed/`, `artifacts/models/`, `reports/`, `.codex/`, `.worktrees/`, or local `AGENTS.md`.
- Keep API routes thin; domain logic belongs under `src/longevity_lab/services/` or `src/longevity_lab/pipeline/`.
- Every PR that changes serving contracts must update `docs/schema_contracts.md`, frontend types, backend tests, and Playwright coverage.
- Every PR that changes data/model behavior must update `docs/feature_status.md`, `docs/data_dictionary.md`, `docs/modeling.md`, and generated artifact/release documentation as applicable.
- A PR is ready only after targeted checks, broader checks where relevant, and local adversarial review report no new P0/P1/P2 findings for the latest hash.

## Dependency Map

1. PR 19 is the foundation for geography-aware serving.
2. PR 20 depends on PR 19 and activates state-year ACS/SVI features in trained artifacts.
3. PR 21 depends on PR 20 and hardens the context UX and evidence copy.
4. PR 22 can run after the current `main`; it expands the causal workbench without serving changes.
5. PR 23 depends on PR 22 and adds heterogeneous-effect reports.
6. PR 24 can run after PR 20 if tree-ensemble artifacts are available.
7. PR 25 depends on PR 24 for uncertainty display consistency, but can start with decision-tree calibration intervals if PR 24 is delayed.
8. PR 26 and PR 27 can run in parallel after current `main`.
9. PR 28 is optional backlog and should wait until PR 20 model ablation patterns are stable.

## PR 19: Geography Serving Foundation

**Branch:** `codex/pr-19-geography-serving-foundation`

**Purpose:** Add explicit state-year geography selection and context lookup infrastructure without activating ACS/SVI in prediction yet.

**Files:**
- Create: `src/longevity_lab/services/context_lookup.py`
- Create: `src/longevity_lab/api/routes/context.py`
- Modify: `src/longevity_lab/api/main.py`
- Modify: `src/longevity_lab/api/schemas.py`
- Modify: `src/longevity_lab/services/metadata_service.py`
- Modify: `src/longevity_lab/services/scenario_service.py`
- Modify: `src/longevity_lab/services/artifact_engine.py`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/state/scenario-context.tsx`
- Modify: `frontend/src/components/scenario-form.tsx`
- Test: `tests/test_api.py`
- Test: `tests/test_context_tables.py`
- Create: `tests/test_context_lookup.py`
- Test: `frontend/e2e/app.spec.ts`
- Docs: `docs/schema_contracts.md`, `docs/data_dictionary.md`, `docs/feature_status.md`

**Implementation prompt:**

```text
You are implementing PR 19: Geography Serving Foundation in the Longevity Lab repo.

Read first:
- AGENTS.md
- docs/roadmap.md
- docs/feature_status.md
- docs/schema_contracts.md
- docs/data_dictionary.md
- docs/superpowers/plans/2026-05-06-remaining-work-pr-roadmap.md

Scope:
- Add explicit geography selection for state-year context only.
- Do not activate ACS/SVI features in prediction in this PR.
- Do not expose county-level prediction semantics, because BRFSS person rows only support state-year joins.
- Keep geography selection separate from lifestyle scenario inputs so the UI does not imply a user can personally change ACS/SVI context like BMI or smoking.

Implementation:
- Add a context lookup service that reads processed state-year context tables when present and returns safe relative metadata when missing.
- Add `GET /api/context/geographies?year=2023` with available state options, selected year, and context readiness.
- Add optional `geography` to scenario compare requests with fields `level`, `state_fips`, and `year`.
- Add bootstrap metadata for supported geography levels and whether context lookup is active.
- Make demo and artifact engines accept geography metadata but ignore ACS/SVI context unless the artifact manifest declares context features.
- Add a frontend state selector under a distinct "Geography context" section, with copy that state context is background context, not a personal behavior.

Acceptance:
- Existing scenario requests without geography remain valid.
- API responses never leak absolute local paths.
- Data Evidence continues to show ACS/SVI as implemented but inactive.
- The Explorer shows selected state context separately from lifestyle inputs.
- No model score changes occur solely from selecting geography until PR 20 activates context-aware artifacts.

Validation:
- pdm run pytest tests/test_context_lookup.py tests/test_api.py tests/test_context_tables.py
- pdm run ruff check src tests
- pdm run mypy src tests
- cd frontend; npm run check
- cd frontend; npm run test:e2e
```

## PR 20: Context-Aware Artifact Training and Activation

**Branch:** `codex/pr-20-context-aware-artifacts`

**Purpose:** Train and serve artifacts that use state-year ACS/SVI context features through the geography lookup contract from PR 19.

**Files:**
- Modify: `conf/train.yaml`
- Modify: `conf/benchmark.yaml`
- Modify: `src/longevity_lab/pipeline/build_integrated_tables.py`
- Modify: `src/longevity_lab/pipeline/modeling.py`
- Modify: `src/longevity_lab/pipeline/train.py`
- Modify: `src/longevity_lab/pipeline/benchmarks.py`
- Modify: `src/longevity_lab/artifacts/manifest.py`
- Modify: `src/longevity_lab/services/artifact_engine.py`
- Modify: `src/longevity_lab/services/evidence_service.py`
- Test: `tests/test_training_pipeline.py`
- Test: `tests/test_benchmarks.py`
- Test: `tests/test_artifact_engine.py`
- Test: `tests/test_evidence_status_api.py`
- Docs: `docs/modeling.md`, `docs/data_dictionary.md`, `docs/schema_contracts.md`, `docs/feature_status.md`, `docs/deployment.md`

**Implementation prompt:**

```text
You are implementing PR 20: Context-Aware Artifact Training and Activation in the Longevity Lab repo.

Read first:
- AGENTS.md
- docs/roadmap.md
- docs/feature_status.md
- docs/modeling.md
- docs/schema_contracts.md
- docs/data_dictionary.md
- docs/superpowers/plans/2026-05-06-remaining-work-pr-roadmap.md

Scope:
- Activate only state-year ACS/SVI features that can join defensibly to BRFSS state-year rows.
- Do not train on county-level ACS/SVI, PLACES, or other aggregate sources as person-level labels.
- Do not activate context features unless the artifact manifest includes the exact context feature list and lookup provenance.

Implementation:
- Add a `context_features` training group with the curated ACS/SVI state-year columns already documented.
- Add benchmark ablations: `no_context`, `air_quality_only`, and `context_plus_air_quality`.
- Persist context feature metadata in the artifact manifest: feature names, source IDs, join keys, data vintage, and caveats.
- Package a compact state-year context lookup table or JSON inside the trusted artifact bundle.
- Update `ArtifactScenarioEngine` so selected geography supplies context features at inference; missing geography uses manifest-declared defaults with a clear caveat.
- Update evidence status so ACS/SVI moves from inactive context to active model source only for artifacts that actually use the features.
- Train a new full artifact bundle outside git, publish it to GitHub Releases, update `render.yaml` SHA, and production-smoke it after merge.

Acceptance:
- Artifact mode scores can change when selected geography changes, and the response explains the state-year context source.
- Model cards show context feature count and ablation lift.
- Evidence status distinguishes active state-year context from still-inactive county-level context.
- Demo mode remains explicitly labeled and does not pretend to use ACS/SVI context.

Validation:
- pdm run pytest tests/test_training_pipeline.py tests/test_benchmarks.py tests/test_artifact_engine.py tests/test_evidence_status_api.py
- pdm run ruff check src tests
- pdm run mypy src tests
- pdm run python -m longevity_lab.pipeline.benchmarks
- pdm run python -m longevity_lab.pipeline.train data.use_sample_if_missing=false
- python scripts/download_model_bundle.py with the published release URL and SHA
- production smoke after Render deploy
```

## PR 21: Context Transparency UX

**Branch:** `codex/pr-21-context-transparency-ux`

**Purpose:** Make geography-aware context understandable in the Explorer, Data Evidence, Model Cards, and Scenario Lab.

**Files:**
- Modify: `frontend/src/pages/ExplorerPage.tsx`
- Modify: `frontend/src/pages/DataEvidencePage.tsx`
- Modify: `frontend/src/pages/ModelCardsPage.tsx`
- Modify: `frontend/src/pages/ScenarioLabPage.tsx`
- Modify: `frontend/src/components/scenario-form.tsx`
- Modify: `frontend/src/components/condition-inspector.tsx`
- Modify: `frontend/src/styles.css`
- Test: `frontend/e2e/app.spec.ts`
- Docs: `docs/feature_status.md`, `docs/schema_contracts.md`

**Implementation prompt:**

```text
You are implementing PR 21: Context Transparency UX in the Longevity Lab repo.

Read first:
- AGENTS.md
- docs/feature_status.md
- docs/schema_contracts.md
- docs/superpowers/plans/2026-05-06-remaining-work-pr-roadmap.md

Scope:
- Improve UX copy and visual separation for state-year geography context.
- Do not introduce new model features or retrain artifacts.
- Do not describe contextual geography as a personal recommendation or causal factor.

Implementation:
- Add a dedicated context card in Explorer showing selected state, context data vintage, and active/inactive status.
- Add condition drill-down caveats that separate personal scenario inputs from contextual state-year features.
- Add Data Evidence grouping for active state-year context, inactive county context, and validation-only PLACES.
- Add Model Cards rows for context ablation lift, subgroup caveats, and context feature lists.
- Add Scenario Lab export rows showing geography selection and context fields used.

Acceptance:
- A user can tell which fields they personally edited and which fields came from state-level context.
- Playwright verifies geography selector, context cards, and evidence/model-card context sections at desktop and mobile widths.
- No UI copy implies diagnosis, treatment, or causal proof.

Validation:
- cd frontend; npm run check
- cd frontend; npm run lint
- cd frontend; npm run build
- cd frontend; npm run test:e2e
```

## PR 22: Causal Workbench Multi-Question Expansion

**Branch:** `codex/pr-22-causal-multi-question-workbench`

**Purpose:** Extend the non-serving causal workbench from smoking only to physical activity, BMI, and alcohol questions already specified in PR 11.

**Files:**
- Modify: `src/longevity_lab/causal/datasets.py`
- Modify: `src/longevity_lab/causal/estimators.py`
- Modify: `src/longevity_lab/causal/reports.py`
- Create: `src/longevity_lab/causal/registry.py`
- Create: `conf/causal/activity_diabetes.yaml`
- Create: `conf/causal/bmi_diabetes.yaml`
- Create: `conf/causal/alcohol_depression.yaml`
- Test: `tests/test_causal_datasets.py`
- Test: `tests/test_causal_reports.py`
- Create: `tests/test_causal_registry.py`
- Docs: `docs/causal_inference.md`, `docs/feature_status.md`

**Implementation prompt:**

```text
You are implementing PR 22: Causal Workbench Multi-Question Expansion in the Longevity Lab repo.

Read first:
- AGENTS.md
- docs/causal_inference.md
- conf/causal/questions.yaml
- docs/feature_status.md
- docs/superpowers/plans/2026-05-06-remaining-work-pr-roadmap.md

Scope:
- Add non-serving causal scripts for physical activity to diabetes, BMI to diabetes, and alcohol to depression.
- Keep all causal outputs outside API and Explorer UI.
- Do not call predictive scenario deltas causal effects.

Implementation:
- Add a causal question registry loader that maps `conf/causal/questions.yaml` entries to concrete run configs.
- Generalize analysis dataset construction for treatment, outcome, weights, exclusions, confounders, and missingness summaries.
- Implement weighted logistic g-computation for each question with overlap diagnostics and balance summaries.
- Add negative-control and sensitivity hooks that write explicit "not run" or "failed diagnostic" statuses when prerequisites are not met.
- Write one Markdown and one JSON report per question under `data/processed/reports/causal/<question_id>/`.

Acceptance:
- Each configured causal question produces an audit report or a clear diagnostic failure report.
- Reports include treatment, outcome, estimand, exclusions, adjustment set, overlap diagnostics, estimate, sensitivity status, and limitations.
- No serving route or frontend page consumes causal estimates.

Validation:
- pdm run pytest tests/test_causal_datasets.py tests/test_causal_reports.py tests/test_causal_registry.py
- pdm run ruff check src tests
- pdm run mypy src tests
- pdm run python -m longevity_lab.causal.reports --question activity_diabetes
- pdm run python -m longevity_lab.causal.reports --question bmi_diabetes
- pdm run python -m longevity_lab.causal.reports --question alcohol_depression
```

## PR 23: Causal Heterogeneous-Effect Reports

**Branch:** `codex/pr-23-causal-heterogeneous-effects`

**Purpose:** Add subgroup and heterogeneous-effect reporting for causal questions without changing predictive serving.

**Files:**
- Modify: `src/longevity_lab/causal/estimators.py`
- Modify: `src/longevity_lab/causal/reports.py`
- Create: `src/longevity_lab/causal/heterogeneity.py`
- Modify: `conf/causal/questions.yaml`
- Test: `tests/test_causal_reports.py`
- Create: `tests/test_causal_heterogeneity.py`
- Docs: `docs/causal_inference.md`, `docs/feature_status.md`

**Implementation prompt:**

```text
You are implementing PR 23: Causal Heterogeneous-Effect Reports in the Longevity Lab repo.

Read first:
- AGENTS.md
- docs/causal_inference.md
- conf/causal/questions.yaml
- docs/superpowers/plans/2026-05-06-remaining-work-pr-roadmap.md

Scope:
- Add subgroup and heterogeneous-effect reports only.
- Keep EconML/DoWhy optional. If optional dependencies are absent, write skipped-method records instead of failing the default install.
- Do not expose causal output through FastAPI or React.

Implementation:
- Add subgroup estimates for age band, sex, race/ethnicity, and state/context strata when columns are present.
- Add a conservative heterogeneity runner with minimum cell-size checks and positivity diagnostics.
- Optionally support CausalForestDML behind an extra dependency; default CI should pass without it.
- Write method caveats and diagnostic warnings into JSON/Markdown reports.

Acceptance:
- Reports never present subgroup effects when sample-size or overlap checks fail.
- Optional estimator skips are explicit and tested.
- Causal reports remain non-serving artifacts.

Validation:
- pdm run pytest tests/test_causal_reports.py tests/test_causal_heterogeneity.py
- pdm run ruff check src tests
- pdm run mypy src tests
```

## PR 24: SHAP Explanation Artifact Support

**Branch:** `codex/pr-24-shap-explanation-artifacts`

**Purpose:** Add model-matched SHAP explanation artifacts for supported tree-ensemble bundles while preserving rule-path explanations for decision trees.

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/longevity_lab/pipeline/modeling.py`
- Modify: `src/longevity_lab/pipeline/train.py`
- Modify: `src/longevity_lab/artifacts/manifest.py`
- Modify: `src/longevity_lab/services/explanations.py`
- Modify: `src/longevity_lab/services/artifact_engine.py`
- Test: `tests/test_training_pipeline.py`
- Test: `tests/test_artifact_engine.py`
- Docs: `docs/modeling.md`, `docs/schema_contracts.md`, `docs/feature_status.md`

**Implementation prompt:**

```text
You are implementing PR 24: SHAP Explanation Artifact Support in the Longevity Lab repo.

Read first:
- AGENTS.md
- docs/modeling.md
- docs/schema_contracts.md
- docs/roadmap.md
- docs/superpowers/plans/2026-05-06-remaining-work-pr-roadmap.md

Scope:
- Add SHAP explanation support only for model families where the trained artifact and dependency support it.
- Keep decision-tree rule-path explanations unchanged.
- Do not compute SHAP values at request time for large background datasets.

Implementation:
- Add optional SHAP dependency under a training/explainability extra.
- During training, save compact background samples and per-condition explainer metadata for supported tree ensembles.
- Extend the manifest with explanation method records: `tree_path`, `tree_shap`, background sample size, feature names, and caveats.
- Update artifact scoring to return typed explanation records from SHAP when available, falling back to rule-path or manifest-declared unavailable records.
- Add tests with tiny synthetic artifacts so CI does not require full training data.

Acceptance:
- Explanation methods in API metadata exactly match artifact manifest methods.
- UI receives `method=tree_shap` only when a SHAP artifact exists.
- Missing optional SHAP dependency produces a skipped training artifact, not a runtime crash.

Validation:
- pdm run pytest tests/test_training_pipeline.py tests/test_artifact_engine.py
- pdm run ruff check src tests
- pdm run mypy src tests
```

## PR 25: Calibration and Conformal Uncertainty

**Branch:** `codex/pr-25-calibration-conformal-uncertainty`

**Purpose:** Provide honest calibrated uncertainty summaries for artifacts that declare uncertainty support.

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/longevity_lab/pipeline/modeling.py`
- Modify: `src/longevity_lab/pipeline/evaluate.py`
- Modify: `src/longevity_lab/artifacts/manifest.py`
- Modify: `src/longevity_lab/services/uncertainty.py`
- Modify: `frontend/src/components/condition-inspector.tsx`
- Modify: `frontend/src/pages/ModelCardsPage.tsx`
- Test: `tests/test_training_pipeline.py`
- Test: `tests/test_artifact_engine.py`
- Test: `tests/test_api.py`
- Test: `frontend/e2e/app.spec.ts`
- Docs: `docs/modeling.md`, `docs/schema_contracts.md`, `docs/feature_status.md`

**Implementation prompt:**

```text
You are implementing PR 25: Calibration and Conformal Uncertainty in the Longevity Lab repo.

Read first:
- AGENTS.md
- docs/modeling.md
- docs/schema_contracts.md
- docs/feature_status.md
- docs/superpowers/plans/2026-05-06-remaining-work-pr-roadmap.md

Scope:
- Add uncertainty only when the artifact manifest declares a method and diagnostics pass.
- Do not display clinical confidence intervals or imply diagnosis.
- Keep MAPIE or conformal dependencies optional unless CI and deployment budgets remain acceptable.

Implementation:
- Add calibration diagnostics: expected calibration error, calibration slope/intercept, and reliability-bin summaries.
- Add conformal or calibration-bin uncertainty summaries with minimum calibration-set size checks.
- Extend artifact manifests with `uncertainty_method`, `confidence_level`, diagnostic thresholds, and caveats.
- Update API and UI copy so uncertainty is "communication uncertainty", not clinical certainty.
- Model Cards should show uncertainty availability, method, and calibration diagnostics by condition.

Acceptance:
- Conditions without valid uncertainty support return `uncertainty=null` and a clear unavailable message.
- Conditions with valid support return typed lower/upper summaries and caveats.
- Playwright verifies both available and unavailable states.

Validation:
- pdm run pytest tests/test_training_pipeline.py tests/test_artifact_engine.py tests/test_api.py
- pdm run ruff check src tests
- pdm run mypy src tests
- cd frontend; npm run check
- cd frontend; npm run test:e2e
```

## PR 26: Mobile and Responsive UX Completion

**Branch:** `codex/pr-26-mobile-responsive-ux`

**Purpose:** Replace the current demo-level responsive pass with tested mobile, tablet, and desktop layouts.

**Files:**
- Modify: `frontend/src/styles.css`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/pages/ExplorerPage.tsx`
- Modify: `frontend/src/pages/DataEvidencePage.tsx`
- Modify: `frontend/src/pages/ModelCardsPage.tsx`
- Modify: `frontend/src/pages/ScenarioLabPage.tsx`
- Modify: `frontend/src/components/body-heatmap.tsx`
- Modify: `frontend/src/components/scenario-form.tsx`
- Test: `frontend/e2e/app.spec.ts`
- Docs: `docs/feature_status.md`

**Implementation prompt:**

```text
You are implementing PR 26: Mobile and Responsive UX Completion in the Longevity Lab repo.

Read first:
- AGENTS.md
- docs/feature_status.md
- docs/schema_contracts.md
- docs/superpowers/plans/2026-05-06-remaining-work-pr-roadmap.md

Scope:
- Fix responsive layout and interaction quality.
- Do not change model or API behavior.
- Do not replace the design system wholesale.

Implementation:
- Add Playwright viewport coverage for 390x844, 768x1024, 1440x1200.
- Ensure navigation wraps or collapses cleanly without horizontal scroll.
- Ensure side-by-side profile editors stack on narrow screens.
- Ensure the anatomy heatmap remains legible and keyboard accessible on mobile.
- Ensure Data Evidence and Model Cards cards stack with readable text and no clipped values.
- Add CSS tokens/breakpoints only where needed.

Acceptance:
- No horizontal page overflow at supported widths.
- All primary pages are readable without zoom on mobile.
- Core Explorer flow works on mobile: select organ, edit scenario, inspect condition, view guidance.
- `docs/feature_status.md` changes mobile/responsive layout from DEMO to DONE.

Validation:
- cd frontend; npm run check
- cd frontend; npm run lint
- cd frontend; npm run build
- cd frontend; npm run test:e2e
```

## PR 27: Ethics and Health Disclaimer Finalization

**Branch:** `codex/pr-27-ethics-disclaimer-finalization`

**Purpose:** Standardize non-diagnostic, health-literacy, data-limitation, and model-limitation language across UI and docs.

**Files:**
- Create: `frontend/src/content/disclaimers.ts`
- Modify: `frontend/src/pages/ExplorerPage.tsx`
- Modify: `frontend/src/pages/DataEvidencePage.tsx`
- Modify: `frontend/src/pages/ModelCardsPage.tsx`
- Modify: `frontend/src/components/condition-inspector.tsx`
- Modify: `docs/quickstart.md`
- Modify: `docs/modeling.md`
- Modify: `docs/schema_contracts.md`
- Modify: `docs/feature_status.md`
- Test: `frontend/e2e/app.spec.ts`

**Implementation prompt:**

```text
You are implementing PR 27: Ethics and Health Disclaimer Finalization in the Longevity Lab repo.

Read first:
- AGENTS.md
- docs/roadmap.md
- docs/modeling.md
- docs/schema_contracts.md
- docs/feature_status.md
- docs/superpowers/plans/2026-05-06-remaining-work-pr-roadmap.md

Scope:
- Standardize copy and placement of non-diagnostic warnings and limitations.
- Do not add medical advice, treatment instructions, or clinician-style triage.
- Keep guidance public-health oriented and citation-backed.

Implementation:
- Create one frontend disclaimer content module used across Explorer, Data Evidence, Model Cards, and drill-down guidance.
- Add distinct copy for prediction, causal reports, environmental/context features, and public-health guidance.
- Add a docs section that states intended use, out-of-scope use, data limitations, fairness caveats, and artifact trust boundaries.
- Add E2E assertions that key non-diagnostic copy is visible on relevant pages.

Acceptance:
- No page says or implies diagnosis, treatment, or causal proof from predictive scenario changes.
- Repeated disclaimer copy comes from a shared content module.
- `docs/feature_status.md` marks ethics/disclaimer finalization DONE.

Validation:
- cd frontend; npm run check
- cd frontend; npm run lint
- cd frontend; npm run build
- cd frontend; npm run test:e2e
- git diff --check
```

## PR 28: Optional Data-Source Candidate Screen

**Branch:** `codex/pr-28-data-source-candidate-screen`

**Purpose:** Evaluate optional later data sources before ingestion so the project does not absorb weak or redundant datasets.

**Files:**
- Create: `docs/data_source_candidate_screen.md`
- Create: `conf/data_source_candidates.yaml`
- Create: `src/longevity_lab/pipeline/source_screening.py`
- Create: `tests/test_source_screening.py`
- Modify: `docs/roadmap.md`
- Modify: `docs/feature_status.md`

**Implementation prompt:**

```text
You are implementing PR 28: Optional Data-Source Candidate Screen in the Longevity Lab repo.

Read first:
- AGENTS.md
- docs/roadmap.md
- docs/datasets.md
- docs/data_dictionary.md
- docs/feature_status.md
- docs/superpowers/plans/2026-05-06-remaining-work-pr-roadmap.md

Scope:
- Evaluate AHRQ, USDA Food Environment/Food Access, County Health Rankings, CDC WONDER, NHANES, and NHIS as candidates only.
- Do not ingest or train on these sources in this PR.
- Do not add sources that require private credentials or manual-only downloads.

Implementation:
- Add a machine-readable candidate registry with source URL, access method, geography/time keys, expected size, likely features, target outcomes, join feasibility, bias caveats, and first-pass decision.
- Add a source-screening CLI that validates required registry fields and writes a Markdown summary.
- Add a decision rubric: public access, join feasibility, prior signal rationale, bias review, operational fit, and ablation plan.
- Update roadmap to point future ingestion PRs to the candidate screen.

Acceptance:
- Every optional source receives a decision: reject, watchlist, context-only, validation-only, or ready-for-ablation.
- No new raw data is downloaded.
- Future ingestion requires passing this screen first.

Validation:
- pdm run pytest tests/test_source_screening.py
- pdm run ruff check src tests
- pdm run mypy src tests
- git diff --check
```

## Current Non-Requested Remaining Item

`docs/feature_status.md` still lists one-command dev bootstrap for Windows and macOS as TODO. It is not included in the requested scope above. If implemented, it should be a separate PR after PR 26 or in parallel with PR 27:

- Branch: `codex/pr-29-dev-bootstrap`
- Scope: dependency install, sample data setup, optional artifact download, local API/frontend launch, and smoke checks.
- Checks: `scripts/check_all.ps1`, `scripts/check_all.sh`, `pdm run pytest`, `cd frontend; npm run build`.

## Recommended Execution Order

1. PR 19 geography serving foundation.
2. PR 20 context-aware artifact activation.
3. PR 21 context transparency UX.
4. PR 27 ethics/disclaimer finalization.
5. PR 26 mobile/responsive UX completion.
6. PR 22 causal multi-question workbench.
7. PR 23 causal heterogeneous-effect reports.
8. PR 24 SHAP explanation artifacts.
9. PR 25 calibration/conformal uncertainty.
10. PR 28 optional data-source candidate screen.

This order puts user-facing semantics and safety before more complex model features, while allowing PR 22/23 and PR 26/27 to run in parallel once PR 19/20 are stable.
