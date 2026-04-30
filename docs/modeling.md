# Modeling

Longevity Lab keeps prediction and interpretation reproducible by separating model training,
benchmarking, and serving.

## Current predictive baseline

- The default artifact bundle trains one calibrated model per condition using `conf/train.yaml`.
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
`annual_aqi` and using only scenario-editable features. All candidates use the same
`FeaturePreprocessor` pipeline and the same train/test split per condition.

Histogram gradient boosting uses scikit-learn's `class_weight="balanced"` by default and can apply
configured monotonic constraints after preprocessing. Constraints are recorded by raw feature name in
the benchmark metrics and model-card manifest; one-hot categorical outputs are left unconstrained.

XGBoost is declared only in the optional `train` dependency group. The benchmark harness does not
import it at module import time. If an XGBoost candidate is configured but the package is not
installed, `metrics.json` records a `status: "skipped"` row with a clear `skip_reason`; calibration
curves and subgroup rows are omitted for that skipped candidate.
