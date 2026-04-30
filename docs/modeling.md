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
- `model_card_manifest.json`: model-card-ready condition summaries selected by average precision.

## Comparisons

The first benchmark grid includes logistic regression and decision-tree baselines plus ablations for
dropping `annual_aqi` and using only scenario-editable features. Gradient-boosted models are deferred
to the next PR so the baseline comparison remains dependency-light and easy to audit.
