# Modeling

Longevity Lab keeps prediction and interpretation reproducible by separating model training,
benchmarking, and serving.

## Current predictive baseline

- The default artifact bundle trains one calibrated model per condition using `conf/train.yaml`.
  Current direct BRFSS labels cover heart disease, chronic lung disease, asthma, stroke,
  depression, diabetes, chronic kidney disease, and arthritis.
- PR 20 activates a curated state-year ACS/SVI context feature group for artifact training.
  These features are joined only by (`state_fips`, `year`) and are not scenario-editable inputs.
- Training uses the shared `FeaturePreprocessor` pipeline so persisted artifacts and API inference use
  the same feature ordering, imputation, boolean coercion, and categorical encoding.
- The decision-tree baseline remains interpretable and produces tree-path explanation artifacts.

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
`HistGradientBoostingClassifier`, and optional XGBoost candidates plus ablations for dropping
`annual_aqi`, dropping PM2.5/ozone pollutant features, dropping all ACS/SVI context
(`no_context`), training on air quality only, training on context plus air quality, and using only
scenario-editable features. All candidates use the same `FeaturePreprocessor` pipeline and the same
train/test split per condition.

Histogram gradient boosting uses scikit-learn's `class_weight="balanced"` by default and can apply
configured monotonic constraints after preprocessing. Constraints are recorded by raw feature name in
the benchmark metrics and model-card manifest; one-hot categorical outputs are left unconstrained.

XGBoost is declared only in the optional `train` dependency group. The benchmark harness does not
import it at module import time. If an XGBoost candidate is configured but the package is not
installed, `metrics.json` records a `status: "skipped"` row with a clear `skip_reason`; calibration
curves and subgroup rows are omitted for that skipped candidate.

## Served explanations and uncertainty

Served condition scores expose typed explanation records in addition to the legacy `key_drivers`
labels. Decision-tree artifacts use the saved rule-path explanation pipeline. Tree-ensemble
artifacts can opt into `shap` explanations when the serving environment has SHAP installed; the API
reports SHAP values as model attributions with a caveat that correlated features can share
attribution and that explanations are not causal effects.

Prediction uncertainty is shown only when a condition artifact declares an uncertainty method in the
manifest. The first supported method is `calibration_interval`, backed by an artifact-side JSON
configuration such as `half_width`, `confidence_level`, and `caveat`.

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
