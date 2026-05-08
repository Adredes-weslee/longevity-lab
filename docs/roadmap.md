# Longevity Lab Product Roadmap

This roadmap defines the independent product direction for Longevity Lab. It supersedes the baseline implementation history in `docs/implementation_plan.md` while preserving the existing local-first monorepo, BRFSS/EPA baseline, FastAPI backend, React frontend, and reproducibility guardrails.

## Product Boundary

Longevity Lab remains a non-diagnostic health-risk communication and scenario-comparison tool. It should not become a clinical decision support system, a treatment recommender, an electronic health record product, or a broad "god app" that absorbs every health-related dataset.

New work must satisfy these constraints:

- Use only public, open, script-downloadable data sources with documented provenance.
- Prefer features with strong prior plausibility, measurable incremental lift, meaningful scenario sensitivity, or clear equity/context value.
- Keep individual prediction, contextual geography, model evaluation, and causal analysis as separate surfaces.
- Label model outputs as predicted associations unless a causal estimand and assumptions have been specified and tested.
- Keep training and inference aligned through persisted preprocessing pipelines and versioned artifact manifests.
- Replace notebook-centric workflows with scripted reports that write logs, metrics, figures, tables, and model cards programmatically.

## End-State Architecture

The target architecture has five layers:

1. **Data registry:** source adapters, downloader scripts, checksums, licenses/terms notes, schema versions, and retrieval dates.
2. **Feature store:** person-year BRFSS features plus contextual state/county/tract-year tables, with join rules recorded in provenance manifests.
3. **Model registry:** calibrated per-condition prediction bundles, benchmark baselines, explainability artifacts, subgroup metrics, and model cards.
4. **Causal workbench:** separate scripts for explicit causal questions, directed acyclic graphs, estimands, sensitivity checks, and assumption reports.
5. **Application:** FastAPI contracts and React pages for scenario comparison, evidence/provenance, model cards, data status, and accessible risk communication.

Current implementation status: the application now includes a Community Context surface that reads
state/county ACS/SVI context, CDC PLACES county context, PLACES aggregate validation reports, and
local causal workbench reports through `GET /api/community/overview`. These are presented as
evidence and research surfaces, not as hidden modifiers to Explorer person-level predictions.

## Data Source Strategy

### Inclusion Screen

Each candidate source must pass this screen before ingestion work starts:

- **Public access:** no private credentials, proprietary datasets, or manual-only downloads.
- **Join feasibility:** clear geography/time keys that can join to BRFSS state-year or contextual county/tract-year tables.
- **Signal rationale:** prior evidence or preliminary EDA suggests relevance to at least one modeled condition.
- **Bias review:** limitations, ecological-fallacy risk, missingness, and demographic coverage are documented.
- **Operational fit:** download size and processing cost are compatible with local development and free-tier deployment constraints.

Optional later sources are tracked in `conf/data_source_candidates.yaml` and summarized in
`docs/data_source_candidate_screen.md`. A future ingestion PR must first move a candidate through
that screen with a decision of `ready-for-ablation`, `context-only`, or `validation-only` for the
specific intended use; `watchlist` and `reject` sources are not eligible for downloader or training
work.

### Source Tiers

| Tier | Source | Use | Initial decision |
| --- | --- | --- | --- |
| Core | [CDC BRFSS 2023 annual data](https://www.cdc.gov/brfss/annual_data/annual_2023.html) and later compatible years | Individual survey features, labels, weights, and scenario inputs | Expand variable coverage and add survey-weight-aware evaluation. |
| Core | [EPA AirData](https://aqs.epa.gov/aqsweb/airdata/download_files.html) | County/state air quality summaries, pollutant-specific exposures, AQI context | Move beyond annual AQI to PM2.5, ozone, and completeness-aware exposure windows. |
| Tier 1 | [CDC PLACES](https://www.cdc.gov/places/tools/data-portal.html) | County/tract/ZCTA chronic-disease and risk-behavior context | Use for contextual maps and external reasonableness checks, not as independent person-level labels. |
| Tier 1 | [Census ACS API](https://www.census.gov/programs-surveys/acs/data/data-via-api.html) | Income, education, poverty, insurance, housing, disability, commute, broadband | Curate a small SDOH set; avoid broad variable dumping. |
| Tier 1 | [CDC/ATSDR SVI](https://www.atsdr.cdc.gov/place-health/php/svi/index.html) | Overall and theme-level social vulnerability | Add as compact equity/context features and subgroup stratification metadata. |
| Watchlist | EPA environmental justice screening data | Environmental justice and demographic burden indicators | Do not include in the first ingestion wave; use ACS, SVI, and EPA AirData unless a current official EPA download endpoint is verified. |
| Tier 1 | [AHRQ community-level health data](https://www.ahrq.gov/data/innovations/clh-data.html) | Curated community-level SDOH and health-system context | `watchlist` in the candidate screen; revisit only after ACS/SVI/PLACES ablations are stable. |
| Tier 2 | [USDA Food Environment Atlas](https://www.ers.usda.gov/data-products/food-environment-atlas/data-access-and-documentation-downloads/) and [Food Access Research Atlas](https://www.ers.usda.gov/data-products/food-access-research-atlas/download-the-data) | Food access, food insecurity, SNAP, stores, obesity/diabetes context | `ready-for-ablation` for a selected county/state-aggregated subset; no broad column dump. |
| Tier 2 | [County Health Rankings](https://www.countyhealthrankings.org/health-data/methodology-and-sources/data-documentation) | County health factors, outcomes, and trend context | `context-only`; use for dashboards/source comparison and avoid training leakage from rankings or outcomes. |
| Tier 2 | [CDC WONDER API](https://wonder.cdc.gov/wonder/help/wonder-api.html) | Mortality context for heart disease, stroke, diabetes, and chronic lower respiratory disease | `validation-only`; national mortality API output is not incidence or geography-specific prevalence. |
| Research | [NHANES public data](https://wwwn.cdc.gov/nchs/nhanes/continuousnhanes/) | Biomarkers and measured health variables for validation experiments | `validation-only`; use as a separate survey pipeline and do not row-join to BRFSS. |
| Research | [NHIS public data](https://www.cdc.gov/nchs/nhis/documentation/index.html) | Alternate self-reported health benchmark | `watchlist`; require a concrete depression or healthcare-access validation question before ingestion. |

## Modeling Strategy

### Prediction Models

The current calibrated decision-tree baseline stays as the interpretable reference. New predictive modeling should be benchmarked against it using the same splits, artifacts, and reporting surfaces.

Recommended model track:

- Logistic regression with splines or monotonic transforms as a transparent baseline.
- Calibrated decision trees and random forests for continuity with the current artifact contract.
- `HistGradientBoostingClassifier` with monotonic constraints where domain direction is defensible, using scikit-learn calibration tools.
- XGBoost as the first external best-in-class tabular model, using documented class-imbalance and monotonic-constraint parameters.
- Optional LightGBM only if XGBoost or scikit-learn models leave material performance gaps.

Current implementation status: the `ensemble-promotion-20260508` benchmark compares all three
tree-ensemble candidates against the calibrated decision-tree baseline. XGBoost is promoted in
`real-20260508-xgboost-shap` because it has the strongest mean ROC-AUC, average precision, and
Brier score across the eight served BRFSS-derived conditions. Histogram gradient boosting and
LightGBM remain supported benchmark candidates for future lower-dependency or alternate-deployment
tradeoffs.

Required metrics:

- ROC-AUC, average precision, Brier score, expected calibration error, calibration slope/intercept, log loss, decision-curve style utility where meaningful.
- Subgroup discrimination and calibration by age band, sex, race/ethnicity where available, geography, and social vulnerability strata.
- Ablation deltas for each new data family, including whether it changes user-facing scenario sensitivity.
- Model-card summaries aligned to [TRIPOD+AI](https://www.bmj.com/content/385/bmj-2023-078378) reporting principles.

### Explanations and Uncertainty

Explanations must match the trained model:

- Decision-tree bundles can keep rule-path explanations.
- Tree-ensemble bundles should use TreeSHAP with clear caveats about correlation and non-causal attribution.
- Scenario deltas should distinguish model-derived contribution, input change, and contextual geography.
- Current artifact bundles can package held-out empirical `calibration_interval` payloads with diagnostics. Future work can compare stricter conformal classifiers such as [MAPIE](https://mapie.readthedocs.io/en/latest/theoretical_description_classification.html) once calibration remains stable on larger artifact families.

Current implementation status: the promoted XGBoost bundle declares SHAP as the served explanation
method in `manifest.json`, keeps SHAP background samples compact, and leaves uncertainty surfaced
through the existing held-out calibration interval payloads.

### Causal Inference

Causal inference is a separate workbench, not a replacement for prediction. The first causal milestone is a spec-only PR that defines a causal question before code estimates effects.

PR 11 establishes the initial spec in `docs/causal_inference.md` and the machine-readable question registry in `conf/causal/questions.yaml`. The registry defines separate questions for smoking, physical activity, BMI, and alcohol, including estimands, adjustment candidates, exclusions, DAG assumptions, negative controls, sensitivity checks, and the required separation from predictive risk scores.

Acceptable causal questions:

- "Among comparable BRFSS adults, what is the estimated association/effect of current smoking on diagnosed chronic lung disease under stated assumptions?"
- "How does meeting physical-activity guidance relate to diabetes risk after adjusting for measured confounders?"
- "Among comparable BRFSS adults, what is the estimated effect of obesity-range BMI on diagnosed diabetes under stated assumptions?"
- "How does heavy alcohol use relate to diagnosed depression after adjustment, sensitivity checks, and reverse-causation review?"
- "Which subgroups show heterogeneous estimated effects for smoking, activity, BMI, or alcohol?"

Required causal workflow:

- State treatment, outcome, population, estimand, adjustment set, and exclusion rules.
- Draw and version a DAG before selecting estimators.
- Use doubly robust or double machine learning methods only when assumptions and diagnostics are recorded.
- Use [DoWhy](https://www.pywhy.org/dowhy/v0.4/index.html) refutation/sensitivity checks and [EconML CausalForestDML](https://www.pywhy.org/EconML/_autosummary/econml.dml.CausalForestDML.html) only for explicit heterogeneous-effect experiments.
- Present causal results separately from the Explorer's predictive risk scores.

## UI and UX Strategy

The UI should move from prototype polish to a user-tested, evidence-transparent product prototype:

- Keep the Explorer as the primary scenario-comparison page.
- Add a Data Evidence page for source provenance, refresh status, schema versions, and feature-ablation lift.
- Add a Community Context page for state/county ACS/SVI context, PLACES aggregate validation, and
  causal workbench report cards while keeping county/PLACES/causal outputs out of individual
  scoring.
- Add Model Cards pages for intended use, population, data vintage, metrics, calibration, subgroup behavior, limitations, and artifact IDs.
- Add a Scenario Lab page for saved scenario comparisons and sensitivity charts.
- Improve the anatomy map with accessible organ labels, keyboard navigation, color-blind-safe palettes, and text alternatives.
- Use CDC clear-communication practices and [WCAG 2.2](https://www.w3.org/TR/wcag/) as acceptance criteria for risk text and interactive visuals.

## Development Workflow

All feature work after this roadmap should use PR-sized branches. Worktrees should be created under `.worktrees/<branch-slug>` after verifying `.worktrees/` is ignored. Branches use the `codex/` prefix unless a human chooses otherwise.

A PR is ready to merge only when:

- The implementation matches the PR prompt in `docs/superpowers/plans/2026-04-30-longevity-lab-expansion.md`.
- The narrowest relevant checks pass locally.
- All drift-sensitive docs/tests/contracts are updated.
- Local adversarial review finds no new P0, P1, or P2 issues against the latest commit hash.
- The branch is opened as a GitHub pull request and the PR description lists checks, data/artifact changes, and limitations.

## Sequenced PR Roadmap

| PR | Theme | Dependency | Outcome |
| --- | --- | --- | --- |
| 00 | Governance and roadmap | None | Local overlay, roadmap, PR plan, worktree policy, and documentation sync. |
| 01 | Artifact-first runtime | 00 | Backend defaults to artifact mode when a valid local bundle exists, with demo fallback explicitly labeled. |
| 02 | Data source registry | 00 | Central source registry, provenance schema, checksum policy, and downloader interface. |
| 03 | BRFSS v2 features | 02 | Expanded BRFSS variable mapping, survey weights, and feature dictionary updates. |
| 04 | EPA pollutant expansion | 02 | PM2.5/ozone/AQI exposure tables with completeness flags and ablation-ready features. |
| 05 | ACS/SVI contextual features | 02 | Curated SDOH context tables and documented geography joins. |
| 06 | PLACES and external validation | 02, 05 | Contextual disease/risk maps and external reasonableness reports. |
| 07 | Scripted EDA reports | 03, 04, 05 | Programmatic EDA figures/tables/logs replacing notebook-as-source workflows. |
| 08 | Modeling benchmark harness | 03, 04, 05, 07 | Reproducible baseline benchmark suite with model-card outputs. |
| 09 | Calibrated GBDT models | 08 | Best-in-class tabular models compared against decision-tree baseline. |
| 10 | Explainability and uncertainty | 09 | Typed SHAP/rule explanations plus calibrated uncertainty summaries. |
| 11 | Causal inference spec | 02 | Spec-only causal questions, DAG assumptions, estimands, exclusions, negative controls, and sensitivity checks without serving changes. PR 12 cannot estimate effects until the relevant PR 03/05 feature contracts exist. |
| 12 | Causal workbench prototype | 11 | Separate scripts for sensitivity-tested causal estimates and heterogeneous-effect exploration. |
| 13 | API contract v2 | 09, 10 | Versioned contracts for context, uncertainty, explanations, and model metadata. |
| 14 | UI information architecture | 13 | Explorer, Data Evidence, Model Cards, Scenario Lab navigation and layout. |
| 15 | Explorer UX upgrade | 14 | Improved anatomy, scenario sensitivity, accessibility, and explainability copy. |
| 16 | Deployment packaging | 13, 14, 15 | Free-tier-ready deployment profile for Render/Vercel plus local artifact strategy. |
| 28 | Optional data-source candidate screen | 20 preferred | Registry, rubric, and CLI screen for AHRQ, USDA, County Health Rankings, CDC WONDER, NHANES, and NHIS before any ingestion work. |

## Deployment Direction

Keep local development and reproducibility as the primary path. For public demos:

- Vercel is suitable for a static React frontend.
- Render is suitable for a small FastAPI API but may cold-start on the free tier.
- Large datasets and trained artifacts should not be bundled into the deployed repo.
- Public demo deployments should use either a small sample artifact or a separately documented artifact retrieval step.
- The UI must clearly display whether it is running demo, sample-artifact, or local full-artifact mode.
