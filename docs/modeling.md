# Modeling

Longevity Lab keeps prediction and interpretation reproducible by separating model training,
benchmarking, and serving.

## Current predictive model

- The default artifact bundle trains one calibrated model per condition using `conf/train.yaml`.
  Current direct BRFSS labels cover heart disease, chronic lung disease, asthma, stroke,
  depression, diabetes, chronic kidney disease, and arthritis.
- PR 20 activates a curated state-year ACS/SVI context feature group for artifact training.
  These features are joined only by (`state_fips`, `year`) and are not scenario-editable inputs.
- Training uses the shared `FeaturePreprocessor` pipeline so persisted artifacts and API inference use
  the same feature ordering, imputation, boolean coercion, and categorical encoding.
- The decision-tree baseline remains available for continuity, but the promoted production
  candidate is an XGBoost tree ensemble with calibrated probabilities and packaged SHAP
  explanation artifacts.

## Benchmark harness

`src/longevity_lab/pipeline/benchmarks.py` runs model families and feature ablations under the same
train/test split for each condition. The default config is `conf/benchmark.yaml`.

Run:

```powershell
pdm run python -m longevity_lab.pipeline.benchmarks --config conf/benchmark.yaml
```

Outputs are written under `reports/benchmarks/<benchmark_id>/` and are intentionally gitignored:

- `benchmark_manifest.json`: dataset, feature contract, split, model configs, ablations, and output map.
- `metrics.json`: per-condition model and ablation metrics.
- `calibration_curves.json`: binned observed-vs-predicted calibration points.
- `subgroup_metrics.parquet`: slice metrics by age, BMI, smoking, AQI, and exercise tiers.
- `model_card_manifest.json`: model-card-ready condition summaries selected by average precision,
  including each candidate's delta against the all-feature decision-tree baseline.

## Comparisons

The benchmark grid includes logistic regression, the calibrated decision-tree baseline,
`HistGradientBoostingClassifier`, optional XGBoost, and optional LightGBM candidates plus ablations for dropping
`annual_aqi`, dropping PM2.5/ozone pollutant features, dropping all ACS/SVI context
(`no_context`), training on air quality only, training on context plus air quality, and using only
scenario-editable features. All candidates use the same `FeaturePreprocessor` pipeline and the same
train/test split per condition.

Histogram gradient boosting uses scikit-learn's `class_weight="balanced"` by default and can apply
configured monotonic constraints after preprocessing. Constraints are recorded by raw feature name in
the benchmark metrics and model-card manifest; one-hot categorical outputs are left unconstrained.

XGBoost and LightGBM are declared only in the optional `train` dependency group. The benchmark
harness does not import either package at module import time. If an optional candidate is configured
but the package is not installed, `metrics.json` records a `status: "skipped"` row with a clear
`skip_reason`; calibration curves and subgroup rows are omitted for that skipped candidate.

The `ensemble-promotion-20260508` benchmark compared logistic regression, the current
decision-tree baseline, histogram gradient boosting, XGBoost, and LightGBM on the full processed
2023 table. XGBoost had the strongest mean discrimination/ranking signal, with mean ROC-AUC
0.7731, mean average precision 0.2759, and mean Brier score 0.0796 across the eight conditions.
That is a mean +0.0131 ROC-AUC, +0.0224 average-precision, and -0.0012 Brier-score improvement
against the decision-tree baseline.

The promoted `real-20260508-xgboost-shap` artifact reports these calibrated test metrics:

| Condition | ROC-AUC | Average precision | Brier score |
| --- | ---: | ---: | ---: |
| Heart disease | 0.8140 | 0.2194 | 0.0549 |
| Chronic lung disease | 0.7905 | 0.2412 | 0.0507 |
| Asthma | 0.6838 | 0.1949 | 0.0847 |
| Stroke | 0.7934 | 0.1184 | 0.0322 |
| Depression | 0.7284 | 0.4163 | 0.1407 |
| Diabetes | 0.8035 | 0.3349 | 0.0922 |
| Kidney disease | 0.7606 | 0.1197 | 0.0365 |
| Arthritis | 0.8105 | 0.5620 | 0.1451 |

## Served explanations and uncertainty

Served condition scores expose typed explanation records in addition to the legacy `key_drivers`
labels. Decision-tree artifacts use the saved rule-path explanation pipeline. Supported
tree-ensemble artifacts can opt into `shap` explanations by packaging a compact background sample
and explainer metadata under the optional `explainability` dependency. The API reports SHAP values
as model attributions with a caveat that correlated features can share attribution and that
explanations are not causal effects. Missing SHAP support is recorded as a skipped explanation
artifact instead of changing the decision-tree rule-path contract.

Prediction uncertainty is shown only when a condition artifact declares an uncertainty method in the
manifest and the bundle-local payload exists. The first supported method is
`calibration_interval`, generated from held-out absolute prediction residuals and packaged as
artifact-side JSON with `half_width`, `confidence_level`, `n_calibration`,
`empirical_coverage`, calibration diagnostics, and a caveat. These intervals are communication
summaries, not clinical confidence intervals.

## Ethics and interpretation limits

The predictive application is intentionally non-diagnostic. Model probabilities and organ summaries
are for educational risk communication and scenario comparison only; they are not medical advice,
diagnosis, screening, treatment guidance, or individual clinical risk certification.

Predictive scenario deltas must not be described as causal effects. Offline causal workbench reports
use separate assumptions, diagnostics, and outputs, and the Explorer does not consume those causal
estimates. SHAP or rule-path explanations are model attributions, not proof that changing a feature
will cause the displayed delta.

Data limitations should be visible wherever users inspect results: BRFSS labels and predictors are
self-reported, environmental and social-context fields can be aggregated, and subgroup coverage can
vary. Public-health guidance links are general cited resources rather than personalized medical
instructions.

Artifact trust boundaries are part of the modeling contract. Trained bundles are trusted local
outputs or verified release assets; they should not be loaded from arbitrary user uploads or
unverified URLs because joblib/pickle-style deserialization is unsafe for untrusted inputs. Deployment
artifact downloads should pin the bundle id and SHA256 digest before enabling artifact mode.

## Context-Aware Artifacts

Context features are active at inference only when `manifest.json` includes `context_features`
metadata with the exact feature list, source IDs, state-year join keys, data vintage, caveats,
default values, and a bundle-local lookup file. The trainer writes a compact
`context_state_year_lookup.json` from the training table when `feature_contract.context_features`
is non-empty.

If a request includes state-year geography and the bundle lookup has a matching row, the artifact
engine injects those manifest-declared context values into the shared preprocessing pipeline. If no
geography is supplied, or the selected state-year is absent from the lookup, the engine uses the
manifest-declared defaults. County-level ACS/SVI, PLACES, or other aggregate context is not used as
person-level prediction input.
