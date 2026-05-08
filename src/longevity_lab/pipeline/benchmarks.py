"""Reproducible model benchmark harness for Longevity Lab."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal, cast

import numpy as np  # type: ignore[import-untyped]
import pandas as pd  # type: ignore[import-untyped]
from sklearn.calibration import CalibratedClassifierCV  # type: ignore[import-untyped]
from sklearn.linear_model import LogisticRegression  # type: ignore[import-untyped]
from sklearn.model_selection import train_test_split  # type: ignore[import-untyped]
from sklearn.pipeline import Pipeline  # type: ignore[import-untyped]
from sklearn.tree import DecisionTreeClassifier  # type: ignore[import-untyped]

from longevity_lab.config_files import config_file_path
from longevity_lab.pipeline.modeling import (
    FeaturePreprocessor,
    OptionalModelDependencyError,
    SampleWeightPipeline,
    TrainingSpec,
    _binary_metrics,
    _bucket_age_band,
    _bucket_aqi_tier,
    _bucket_bmi_band,
    _bucket_exercise_tier,
    _bucket_smoker,
    _features_for_condition,
    _predict_positive_class,
    _safe_cv_folds,
    _sample_weights_for_training,
    build_training_spec,
    load_training_frame,
    make_hist_gradient_boosting_pipeline,
    make_lightgbm_pipeline,
    make_xgboost_pipeline,
)

BenchmarkModelKind = Literal[
    "logistic_regression",
    "decision_tree",
    "hist_gradient_boosting",
    "lightgbm",
    "xgboost",
]


@dataclass(frozen=True, slots=True)
class BenchmarkModelSpec:
    """Configuration for one benchmark model family."""

    model_id: str
    kind: BenchmarkModelKind
    params: dict[str, Any]
    class_imbalance_strategy: str | None = None
    monotonic_constraints: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class BenchmarkAblationSpec:
    """Feature ablation variant run under the same train/test split."""

    variant_id: str
    display_name: str
    drop_features: tuple[str, ...] = ()
    keep_features: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class BenchmarkSpec:
    """Concrete benchmark configuration."""

    benchmark_id: str
    training_spec: TrainingSpec
    output_dir: Path
    force_overwrite: bool
    models: tuple[BenchmarkModelSpec, ...]
    ablations: tuple[BenchmarkAblationSpec, ...]
    min_slice_rows: int
    calibration_bins: int


@dataclass(frozen=True, slots=True)
class BenchmarkResult:
    """Paths written by a benchmark run."""

    output_dir: Path
    manifest_path: Path
    metrics_path: Path
    calibration_path: Path
    subgroup_metrics_path: Path
    model_card_manifest_path: Path


def default_benchmark_config_path() -> Path:
    """Return the repo-local benchmark config path."""
    return config_file_path("benchmark.yaml")


def load_benchmark_spec(path: Path | None = None) -> BenchmarkSpec:
    """Load a JSON-compatible benchmark config file."""
    config_path = path or default_benchmark_config_path()
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError("Benchmark config must be a mapping.")
    return build_benchmark_spec(cast(dict[str, Any], payload))


def build_benchmark_spec(raw_cfg: dict[str, Any]) -> BenchmarkSpec:
    """Convert a raw config mapping into a typed benchmark spec."""
    training_spec = build_training_spec(cast(dict[str, Any], raw_cfg["training_spec"]))
    benchmark_id = str(
        raw_cfg.get("benchmark_id") or dt.datetime.now(dt.UTC).strftime("benchmark-%Y%m%dT%H%M%SZ")
    )
    output_cfg = cast(dict[str, Any], raw_cfg.get("output", {}))
    output_base_dir = Path(str(output_cfg.get("base_dir", "reports/benchmarks")))
    output_dir = output_base_dir / benchmark_id
    models = tuple(
        BenchmarkModelSpec(
            model_id=str(item["model_id"]),
            kind=cast(BenchmarkModelKind, str(item["kind"])),
            params=dict(cast(dict[str, Any], item.get("params", {}))),
            class_imbalance_strategy=(
                str(item["class_imbalance_strategy"])
                if item.get("class_imbalance_strategy")
                else None
            ),
            monotonic_constraints=_parse_monotonic_constraints(
                cast(dict[str, Any], item.get("monotonic_constraints", {}))
            ),
        )
        for item in cast(Sequence[dict[str, Any]], raw_cfg["models"])
    )
    ablations = tuple(
        BenchmarkAblationSpec(
            variant_id=str(item["variant_id"]),
            display_name=str(item.get("display_name", item["variant_id"])),
            drop_features=tuple(str(value) for value in item.get("drop_features", [])),
            keep_features=tuple(str(value) for value in item.get("keep_features", [])),
        )
        for item in cast(Sequence[dict[str, Any]], raw_cfg.get("ablations", []))
    )
    if not any(ablation.variant_id == "all_features" for ablation in ablations):
        ablations = (
            BenchmarkAblationSpec(
                variant_id="all_features",
                display_name="All configured features",
            ),
            *ablations,
        )
    return BenchmarkSpec(
        benchmark_id=benchmark_id,
        training_spec=training_spec,
        output_dir=output_dir,
        force_overwrite=bool(output_cfg.get("force_overwrite", False)),
        models=models,
        ablations=ablations,
        min_slice_rows=int(raw_cfg.get("subgroups", {}).get("min_rows", 200)),
        calibration_bins=int(raw_cfg.get("calibration", {}).get("bins", 10)),
    )


def _parse_monotonic_constraints(raw_constraints: dict[str, Any]) -> dict[str, int]:
    constraints: dict[str, int] = {}
    for feature_name, direction in raw_constraints.items():
        value = int(direction)
        if value not in {-1, 0, 1}:
            raise ValueError(
                f"Monotonic constraint for {feature_name!r} must be -1, 0, or 1 "
                f"(got {direction!r})."
            )
        constraints[str(feature_name)] = value
    return constraints


def run_benchmark(spec: BenchmarkSpec) -> BenchmarkResult:
    """Run all benchmark models and persist metrics/report artifacts."""
    data_frame, dataset_path = load_training_frame(spec.training_spec)
    _prepare_output_dir(spec.output_dir, force_overwrite=spec.force_overwrite)

    metrics_rows: list[dict[str, Any]] = []
    calibration_rows: list[dict[str, Any]] = []
    subgroup_rows: list[dict[str, Any]] = []

    for condition_id, label_column in spec.training_spec.conditions.items():
        condition_features = _features_for_condition(spec.training_spec, condition_id=condition_id)
        prepared = _prepare_condition_data(
            data_frame,
            condition_features=condition_features,
            label_column=label_column,
            spec=spec.training_spec,
        )
        for ablation in spec.ablations:
            variant_features = _variant_features(condition_features, ablation)
            for model_spec in spec.models:
                outcome = _fit_and_score_model(
                    prepared,
                    model_spec=model_spec,
                    ablation=ablation,
                    feature_names=variant_features,
                    condition_id=condition_id,
                    label_column=label_column,
                    spec=spec,
                )
                metrics_rows.append(outcome["metrics"])
                calibration_rows.extend(outcome["calibration"])
                subgroup_rows.extend(outcome["subgroups"])

    metrics_path = spec.output_dir / "metrics.json"
    calibration_path = spec.output_dir / "calibration_curves.json"
    subgroup_metrics_path = spec.output_dir / "subgroup_metrics.parquet"
    model_card_manifest_path = spec.output_dir / "model_card_manifest.json"
    manifest_path = spec.output_dir / "benchmark_manifest.json"

    metrics_path.write_text(_json_dumps(metrics_rows), encoding="utf-8")
    calibration_path.write_text(_json_dumps(calibration_rows), encoding="utf-8")
    pd.DataFrame(subgroup_rows).to_parquet(subgroup_metrics_path, index=False)
    model_card_manifest_path.write_text(
        _json_dumps(_model_card_manifest(metrics_rows)),
        encoding="utf-8",
    )
    manifest_path.write_text(
        _json_dumps(
            {
                "benchmark_id": spec.benchmark_id,
                "created_at": dt.datetime.now(dt.UTC).isoformat(),
                "dataset_path": dataset_path.as_posix(),
                "training_feature_contract": spec.training_spec.feature_contract.to_dict(),
                "configured_features": list(spec.training_spec.features),
                "conditions": spec.training_spec.conditions,
                "split": {
                    "test_size": spec.training_spec.test_size,
                    "random_state": spec.training_spec.random_state,
                },
                "models": [asdict(model) for model in spec.models],
                "ablations": [asdict(ablation) for ablation in spec.ablations],
                "outputs": {
                    "metrics": metrics_path.name,
                    "calibration_curves": calibration_path.name,
                    "subgroup_metrics": subgroup_metrics_path.name,
                    "model_card_manifest": model_card_manifest_path.name,
                },
            }
        ),
        encoding="utf-8",
    )

    return BenchmarkResult(
        output_dir=spec.output_dir,
        manifest_path=manifest_path,
        metrics_path=metrics_path,
        calibration_path=calibration_path,
        subgroup_metrics_path=subgroup_metrics_path,
        model_card_manifest_path=model_card_manifest_path,
    )


def _prepare_output_dir(path: Path, *, force_overwrite: bool) -> None:
    if path.exists():
        if not force_overwrite:
            raise FileExistsError(f"Benchmark output already exists: {path}")
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def _variant_features(
    condition_features: tuple[str, ...],
    ablation: BenchmarkAblationSpec,
) -> tuple[str, ...]:
    if ablation.keep_features:
        allowed = set(ablation.keep_features)
        features = tuple(feature for feature in condition_features if feature in allowed)
    else:
        dropped = set(ablation.drop_features)
        features = tuple(feature for feature in condition_features if feature not in dropped)
    if not features:
        raise ValueError(f"Ablation {ablation.variant_id} removes all condition features.")
    return features


def _prepare_condition_data(
    data_frame: pd.DataFrame,
    *,
    condition_features: tuple[str, ...],
    label_column: str,
    spec: TrainingSpec,
) -> dict[str, Any]:
    labels = pd.to_numeric(data_frame[label_column], errors="coerce")
    mask = labels.notna()
    feature_frame = data_frame.loc[mask, list(condition_features)].reset_index(drop=True)
    label_series = labels.loc[mask].astype(int).reset_index(drop=True)
    weights = _sample_weights_for_training(data_frame, spec=spec)
    weights = weights.loc[mask].reset_index(drop=True) if weights is not None else None
    indices = np.arange(len(label_series))
    train_idx, test_idx = train_test_split(
        indices,
        test_size=spec.test_size,
        random_state=spec.random_state,
        stratify=label_series,
    )
    return {
        "features": feature_frame,
        "labels": label_series,
        "weights": weights,
        "train_idx": train_idx,
        "test_idx": test_idx,
    }


def _fit_and_score_model(
    prepared: dict[str, Any],
    *,
    model_spec: BenchmarkModelSpec,
    ablation: BenchmarkAblationSpec,
    feature_names: tuple[str, ...],
    condition_id: str,
    label_column: str,
    spec: BenchmarkSpec,
) -> dict[str, Any]:
    feature_frame = cast(pd.DataFrame, prepared["features"])
    labels = cast(pd.Series, prepared["labels"])
    weights = cast(pd.Series | None, prepared["weights"])
    train_idx = cast(np.ndarray, prepared["train_idx"])
    test_idx = cast(np.ndarray, prepared["test_idx"])

    x_train = feature_frame.loc[:, list(feature_names)].iloc[train_idx].reset_index(drop=True)
    x_test = feature_frame.loc[:, list(feature_names)].iloc[test_idx].reset_index(drop=True)
    y_train = labels.iloc[train_idx].reset_index(drop=True)
    y_test = labels.iloc[test_idx].reset_index(drop=True)
    w_train = weights.iloc[train_idx].reset_index(drop=True) if weights is not None else None
    w_test = weights.iloc[test_idx].reset_index(drop=True) if weights is not None else None

    calibration_folds = _safe_cv_folds(y_train, requested_folds=spec.training_spec.calibration_cv)
    metadata_fields = _model_run_metadata(
        model_spec=model_spec,
        spec=spec,
        calibration_folds=calibration_folds,
    )
    try:
        model = _fit_calibrated_benchmark_model(
            x_train,
            y_train,
            sample_weight=w_train,
            feature_names=feature_names,
            model_spec=model_spec,
            spec=spec,
            calibration_folds=calibration_folds,
        )
    except OptionalModelDependencyError as exc:
        return {
            "metrics": _skipped_metrics_row(
                condition_id=condition_id,
                label_column=label_column,
                model_spec=model_spec,
                ablation=ablation,
                feature_names=feature_names,
                rows_train=len(x_train),
                rows_test=len(x_test),
                positive_rate_test=_weighted_positive_rate(y_test, sample_weight=w_test),
                skip_reason=str(exc),
                metadata_fields=metadata_fields,
            ),
            "calibration": [],
            "subgroups": [],
        }
    probabilities = _predict_positive_class(model, x_test)
    metrics = _binary_metrics(y_test, probabilities, sample_weight=w_test)
    metrics_row: dict[str, Any] = {
        "condition_id": condition_id,
        "label_column": label_column,
        "model_id": model_spec.model_id,
        "model_kind": model_spec.kind,
        "variant_id": ablation.variant_id,
        "variant_display_name": ablation.display_name,
        "features": list(feature_names),
        "n_features": len(feature_names),
        "rows_train": len(x_train),
        "rows_test": len(x_test),
        "positive_rate_test": _weighted_positive_rate(y_test, sample_weight=w_test),
        "status": "ok",
        "skip_reason": None,
        **metadata_fields,
        **{f"test_{key}": value for key, value in metrics.items()},
    }
    prediction_frame = feature_frame.iloc[test_idx].reset_index(drop=True).copy()
    prediction_frame[label_column] = y_test.to_numpy()
    prediction_frame["predicted_probability"] = probabilities
    if w_test is not None:
        prediction_frame["sample_weight"] = w_test.to_numpy()
    subgroups = _benchmark_prediction_slices(
        prediction_frame,
        condition_id=condition_id,
        label_column=label_column,
        model_id=model_spec.model_id,
        variant_id=ablation.variant_id,
        min_rows=spec.min_slice_rows,
    )
    return {
        "metrics": metrics_row,
        "calibration": _calibration_rows(
            y_test,
            probabilities,
            sample_weight=w_test,
            condition_id=condition_id,
            model_id=model_spec.model_id,
            variant_id=ablation.variant_id,
            bins=spec.calibration_bins,
        ),
        "subgroups": subgroups,
    }


def _skipped_metrics_row(
    *,
    condition_id: str,
    label_column: str,
    model_spec: BenchmarkModelSpec,
    ablation: BenchmarkAblationSpec,
    feature_names: tuple[str, ...],
    rows_train: int,
    rows_test: int,
    positive_rate_test: float,
    skip_reason: str,
    metadata_fields: dict[str, Any],
) -> dict[str, Any]:
    return {
        "condition_id": condition_id,
        "label_column": label_column,
        "model_id": model_spec.model_id,
        "model_kind": model_spec.kind,
        "variant_id": ablation.variant_id,
        "variant_display_name": ablation.display_name,
        "features": list(feature_names),
        "n_features": len(feature_names),
        "rows_train": rows_train,
        "rows_test": rows_test,
        "positive_rate_test": positive_rate_test,
        "status": "skipped",
        "skip_reason": skip_reason,
        **metadata_fields,
        "test_average_precision": None,
        "test_roc_auc": None,
        "test_brier_score": None,
    }


def _model_run_metadata(
    *,
    model_spec: BenchmarkModelSpec,
    spec: BenchmarkSpec,
    calibration_folds: int,
) -> dict[str, Any]:
    return {
        "calibration_method": spec.training_spec.calibration_method,
        "calibration_cv_folds": calibration_folds,
        "class_imbalance_strategy": _class_imbalance_strategy(model_spec),
        "monotonic_constraints": dict(model_spec.monotonic_constraints),
    }


def _class_imbalance_strategy(model_spec: BenchmarkModelSpec) -> str:
    if model_spec.class_imbalance_strategy:
        return model_spec.class_imbalance_strategy
    if model_spec.kind == "xgboost":
        return "scale_pos_weight"
    if model_spec.kind == "lightgbm" and model_spec.params.get("class_weight") == "balanced":
        return "class_weight_balanced"
    class_weight = model_spec.params.get("class_weight")
    if class_weight == "balanced":
        return "class_weight_balanced"
    if class_weight is not None:
        return "class_weight_custom"
    return "none"


def _fit_calibrated_benchmark_model(
    x_train: pd.DataFrame,
    y_train: pd.Series,
    *,
    sample_weight: pd.Series | None,
    feature_names: tuple[str, ...],
    model_spec: BenchmarkModelSpec,
    spec: BenchmarkSpec,
    calibration_folds: int,
) -> CalibratedClassifierCV | Pipeline:
    base_pipeline = _make_benchmark_pipeline(
        feature_names=feature_names,
        model_spec=model_spec,
        random_state=spec.training_spec.random_state,
        y_train=y_train,
        sample_weight=sample_weight,
    )
    if calibration_folds < 2:
        base_pipeline.fit(x_train, y_train, sample_weight=sample_weight)
        return base_pipeline
    calibrated = CalibratedClassifierCV(
        estimator=base_pipeline,
        method=spec.training_spec.calibration_method,
        cv=calibration_folds,
    )
    calibrated.fit(x_train, y_train, sample_weight=sample_weight)
    return calibrated


def _make_benchmark_pipeline(
    *,
    feature_names: tuple[str, ...],
    model_spec: BenchmarkModelSpec,
    random_state: int,
    y_train: pd.Series,
    sample_weight: pd.Series | None,
) -> SampleWeightPipeline:
    params = dict(model_spec.params)
    if model_spec.kind == "logistic_regression":
        params.setdefault("max_iter", 1000)
        params.setdefault("class_weight", "balanced")
        params.setdefault("solver", "lbfgs")
        model = LogisticRegression(**params)
    elif model_spec.kind == "decision_tree":
        params.setdefault("class_weight", "balanced")
        params.setdefault("random_state", random_state)
        model = DecisionTreeClassifier(**params)
    elif model_spec.kind == "hist_gradient_boosting":
        model_params = dict(params)
        model_params.setdefault("class_weight", "balanced")
        return make_hist_gradient_boosting_pipeline(
            feature_names=feature_names,
            params=model_params,
            monotonic_constraints=model_spec.monotonic_constraints,
            random_state=random_state,
        )
    elif model_spec.kind == "xgboost":
        return make_xgboost_pipeline(
            feature_names=feature_names,
            params=params,
            monotonic_constraints=model_spec.monotonic_constraints,
            random_state=random_state,
            class_balance_scale=_class_balance_scale(y_train, sample_weight=sample_weight),
        )
    elif model_spec.kind == "lightgbm":
        model_params = dict(params)
        model_params.setdefault("class_weight", "balanced")
        return make_lightgbm_pipeline(
            feature_names=feature_names,
            params=model_params,
            monotonic_constraints=model_spec.monotonic_constraints,
            random_state=random_state,
        )
    else:
        raise ValueError(f"Unsupported benchmark model kind: {model_spec.kind}")
    return SampleWeightPipeline(
        steps=[
            ("preprocess", FeaturePreprocessor(feature_names=feature_names)),
            ("model", model),
        ]
    )


def _class_balance_scale(labels: pd.Series, *, sample_weight: pd.Series | None) -> float | None:
    y = labels.astype(int).reset_index(drop=True)
    if sample_weight is None:
        weights = pd.Series(np.ones(len(y)), index=y.index)
    else:
        weights = pd.to_numeric(sample_weight, errors="coerce").fillna(0.0).reset_index(drop=True)
    positive_weight = float(weights.loc[y == 1].sum())
    negative_weight = float(weights.loc[y == 0].sum())
    if positive_weight <= 0.0 or negative_weight <= 0.0:
        return None
    return negative_weight / positive_weight


def _weighted_positive_rate(labels: pd.Series, *, sample_weight: pd.Series | None) -> float:
    values = labels.astype(float)
    if sample_weight is None:
        return float(values.mean())
    weights = pd.to_numeric(sample_weight, errors="coerce").astype("float64")
    valid = weights.notna() & (weights > 0)
    if not bool(valid.any()):
        return float(values.mean())
    return float(np.average(values.loc[valid], weights=weights.loc[valid]))


def _benchmark_prediction_slices(
    frame: pd.DataFrame,
    *,
    condition_id: str,
    label_column: str,
    model_id: str,
    variant_id: str,
    min_rows: int,
) -> list[dict[str, Any]]:
    slice_series_by_dimension = {
        "age_band": _bucket_age_band(frame["age"]),
        "bmi_band": _bucket_bmi_band(frame["bmi"]),
        "smoker_status": _bucket_smoker(frame["smoker"]),
        "aqi_tier": _bucket_aqi_tier(frame["annual_aqi"]),
        "exercise_tier": _bucket_exercise_tier(frame["exercise_minutes_per_week"]),
    }
    rows: list[dict[str, Any]] = []
    for slice_dimension, slice_series in slice_series_by_dimension.items():
        grouped = frame.assign(_slice_value=slice_series).groupby(
            "_slice_value", dropna=False, sort=True
        )
        for slice_value, slice_frame in grouped:
            rows.append(
                {
                    "model_id": model_id,
                    "variant_id": variant_id,
                    **_benchmark_slice_metrics_row(
                        slice_frame,
                        condition_id=condition_id,
                        label_column=label_column,
                        slice_dimension=slice_dimension,
                        slice_value=str(slice_value),
                        min_rows=min_rows,
                    ),
                }
            )
    return rows


def _benchmark_slice_metrics_row(
    frame: pd.DataFrame,
    *,
    condition_id: str,
    label_column: str,
    slice_dimension: str,
    slice_value: str,
    min_rows: int,
) -> dict[str, Any]:
    labels = pd.to_numeric(frame[label_column], errors="coerce")
    probabilities = pd.to_numeric(frame["predicted_probability"], errors="coerce")
    weights = (
        pd.to_numeric(frame["sample_weight"], errors="coerce")
        if "sample_weight" in frame.columns
        else None
    )
    mask = labels.notna() & probabilities.notna()
    labels = labels.loc[mask].astype(int).reset_index(drop=True)
    probabilities = probabilities.loc[mask].astype(float).reset_index(drop=True)
    weights = weights.loc[mask].reset_index(drop=True) if weights is not None else None

    n_rows = int(len(labels))
    n_positive = int(labels.sum()) if n_rows else 0
    n_negative = n_rows - n_positive
    positive_rate = _weighted_positive_rate(labels, sample_weight=weights) if n_rows else None
    unweighted_positive_rate = float(labels.mean()) if n_rows else None
    mean_probability = _weighted_mean(probabilities, sample_weight=weights) if n_rows else None
    weighted_rows = (
        float(pd.to_numeric(weights, errors="coerce").sum()) if weights is not None else n_rows
    )
    calibration_gap = (
        abs(mean_probability - positive_rate)
        if mean_probability is not None and positive_rate is not None
        else None
    )

    status = "ok"
    if n_rows < min_rows:
        status = "too_small"
    elif len(labels.unique()) < 2:
        status = "single_class"

    metrics: dict[str, float | None] = {
        "average_precision": None,
        "roc_auc": None,
        "brier_score": None,
    }
    if status == "ok":
        metrics = _binary_metrics(labels, probabilities.to_numpy(), sample_weight=weights)

    return {
        "condition_id": condition_id,
        "slice_dimension": slice_dimension,
        "slice_value": slice_value,
        "n_rows": n_rows,
        "weighted_rows": weighted_rows,
        "n_positive": n_positive,
        "n_negative": n_negative,
        "positive_rate": positive_rate,
        "unweighted_positive_rate": unweighted_positive_rate,
        "mean_predicted_probability": mean_probability,
        "calibration_gap": calibration_gap,
        "average_precision": metrics["average_precision"],
        "roc_auc": metrics["roc_auc"],
        "brier_score": metrics["brier_score"],
        "status": status,
    }


def _weighted_mean(values: pd.Series, *, sample_weight: pd.Series | None) -> float:
    numeric = pd.to_numeric(values, errors="coerce").astype("float64")
    if sample_weight is None:
        return float(numeric.mean())
    weights = pd.to_numeric(sample_weight, errors="coerce").astype("float64")
    valid = numeric.notna() & weights.notna() & (weights > 0)
    if not bool(valid.any()):
        return float(numeric.mean())
    return float(np.average(numeric.loc[valid], weights=weights.loc[valid]))


def _calibration_rows(
    y_true: pd.Series,
    probabilities: np.ndarray,
    *,
    sample_weight: pd.Series | None,
    condition_id: str,
    model_id: str,
    variant_id: str,
    bins: int,
) -> list[dict[str, Any]]:
    if len(np.unique(y_true)) < 2:
        return []
    rows: list[dict[str, Any]] = []
    labels = y_true.reset_index(drop=True).astype(float)
    probability_series = pd.Series(probabilities).astype(float)
    weights = (
        sample_weight.reset_index(drop=True).astype(float)
        if sample_weight is not None
        else pd.Series(np.ones(len(labels)))
    )
    bin_ids = pd.cut(
        probability_series,
        bins=np.linspace(0.0, 1.0, bins + 1),
        labels=False,
        include_lowest=True,
    )
    for bin_index in range(bins):
        mask = bin_ids == bin_index
        if not bool(mask.any()):
            continue
        bin_weights = weights.loc[mask]
        rows.append(
            {
                "condition_id": condition_id,
                "model_id": model_id,
                "variant_id": variant_id,
                "bin_index": bin_index,
                "n_rows": int(mask.sum()),
                "weighted_rows": float(bin_weights.sum()),
                "mean_predicted_probability": _weighted_mean(
                    probability_series.loc[mask],
                    sample_weight=bin_weights,
                ),
                "observed_positive_rate": _weighted_positive_rate(
                    labels.loc[mask],
                    sample_weight=bin_weights,
                ),
            }
        )
    return rows


def _model_card_manifest(metrics_rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in metrics_rows:
        grouped.setdefault(str(row["condition_id"]), []).append(row)
    condition_cards = []
    for condition_id, rows in sorted(grouped.items()):
        baseline = _decision_tree_baseline_row(rows)
        scored_rows = [row for row in rows if row.get("test_average_precision") is not None]
        best = max(scored_rows or rows, key=lambda item: _metric_sort_value(item))
        condition_cards.append(
            {
                "condition_id": condition_id,
                "selected_by": "highest test_average_precision in benchmark grid",
                "best_model_id": best["model_id"],
                "best_variant_id": best["variant_id"],
                "test_average_precision": best["test_average_precision"],
                "test_roc_auc": best["test_roc_auc"],
                "test_brier_score": best["test_brier_score"],
                "candidate_count": len(rows),
                "decision_tree_baseline_model_id": (
                    str(baseline["model_id"]) if baseline is not None else None
                ),
                "decision_tree_baseline_variant_id": (
                    str(baseline["variant_id"]) if baseline is not None else None
                ),
                "best_delta_vs_decision_tree_baseline": _metric_delta(
                    best,
                    baseline,
                    metric_name="test_average_precision",
                ),
                "benchmark_candidates": [
                    _model_card_candidate(row, baseline=baseline) for row in rows
                ],
            }
        )
    return {
        "schema_version": 1,
        "created_at": dt.datetime.now(dt.UTC).isoformat(),
        "condition_cards": condition_cards,
    }


def _metric_sort_value(row: dict[str, Any]) -> float:
    value = row.get("test_average_precision")
    return float(value) if value is not None else -1.0


def _decision_tree_baseline_row(rows: Sequence[dict[str, Any]]) -> dict[str, Any] | None:
    decision_tree_rows = [row for row in rows if row.get("model_kind") == "decision_tree"]
    for row in decision_tree_rows:
        if row.get("variant_id") == "all_features":
            return row
    return decision_tree_rows[0] if decision_tree_rows else None


def _model_card_candidate(
    row: dict[str, Any],
    *,
    baseline: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "model_id": row["model_id"],
        "model_kind": row["model_kind"],
        "variant_id": row["variant_id"],
        "status": row.get("status", "ok"),
        "skip_reason": row.get("skip_reason"),
        "test_average_precision": row.get("test_average_precision"),
        "test_roc_auc": row.get("test_roc_auc"),
        "test_brier_score": row.get("test_brier_score"),
        "delta_vs_decision_tree_baseline": _metric_delta(
            row,
            baseline,
            metric_name="test_average_precision",
        ),
        "class_imbalance_strategy": row.get("class_imbalance_strategy"),
        "monotonic_constraints": row.get("monotonic_constraints", {}),
    }


def _metric_delta(
    row: dict[str, Any],
    baseline: dict[str, Any] | None,
    *,
    metric_name: str,
) -> float | None:
    if baseline is None:
        return None
    value = row.get(metric_name)
    baseline_value = baseline.get(metric_name)
    if value is None or baseline_value is None:
        return None
    return float(value) - float(baseline_value)


def _json_dumps(payload: object) -> str:
    return json.dumps(_json_safe(payload), indent=2) + "\n"


def _json_safe(value: object) -> object:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    if isinstance(value, np.ndarray):
        return [_json_safe(item) for item in value.tolist()]
    if pd.isna(value):
        return None
    return value


def main(argv: list[str] | None = None) -> None:
    """CLI entrypoint for the benchmark harness."""
    parser = argparse.ArgumentParser(description="Run reproducible model benchmarks.")
    parser.add_argument(
        "--config",
        type=Path,
        default=default_benchmark_config_path(),
        help="Benchmark config path.",
    )
    args = parser.parse_args(argv)
    result = run_benchmark(load_benchmark_spec(Path(args.config)))
    print(f"Benchmark written: {result.output_dir}")
    print(f"Manifest: {result.manifest_path}")
    print(f"Metrics: {result.metrics_path}")


if __name__ == "__main__":
    main()
