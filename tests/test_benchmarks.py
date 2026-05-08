"""Tests for the reproducible benchmark harness."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pandas as pd  # type: ignore[import-untyped]
from pytest import MonkeyPatch

import longevity_lab.pipeline.modeling as modeling_module
from longevity_lab.pipeline.benchmarks import (
    build_benchmark_spec,
    load_benchmark_spec,
    run_benchmark,
)


def _write_training_frame(path: Path, *, rows: int = 240) -> None:
    age = [25 + (idx % 55) for idx in range(rows)]
    bmi = [20.0 + (idx % 18) * 0.8 for idx in range(rows)]
    smoker = [(idx % 5) == 0 for idx in range(rows)]
    alcohol = [idx % 21 for idx in range(rows)]
    exercise = [30 + (idx % 12) * 20 for idx in range(rows)]
    annual_aqi = [40 + (idx % 9) * 12 for idx in range(rows)]
    frame = pd.DataFrame(
        {
            "age": age,
            "bmi": bmi,
            "smoker": smoker,
            "alcohol_servings_per_week": alcohol,
            "exercise_minutes_per_week": exercise,
            "annual_aqi": annual_aqi,
            "sex": ["female" if idx % 2 == 0 else "male" for idx in range(rows)],
            "race_ethnicity": [
                ["white_non_hispanic", "black_non_hispanic", "hispanic"][idx % 3]
                for idx in range(rows)
            ],
            "has_healthcare_coverage": [(idx % 11) != 0 for idx in range(rows)],
            "has_personal_doctor": [(idx % 7) != 0 for idx in range(rows)],
            "cost_barrier_to_care": [(idx % 13) == 0 for idx in range(rows)],
            "last_checkup_within_year": [(idx % 5) != 0 for idx in range(rows)],
            "sleep_hours_per_night": [5 + (idx % 5) for idx in range(rows)],
            "physical_health_days": [idx % 31 for idx in range(rows)],
            "mental_health_days": [(idx * 2) % 31 for idx in range(rows)],
            "label_heart_disease": [
                int(item_age > 60 or item_bmi > 32 or item_smoker)
                for item_age, item_bmi, item_smoker in zip(age, bmi, smoker, strict=True)
            ],
            "label_chronic_lung_disease": [
                int(item_smoker or item_aqi > 110)
                for item_smoker, item_aqi in zip(smoker, annual_aqi, strict=True)
            ],
            "survey_weight": [1.0 + (idx % 5) * 0.2 for idx in range(rows)],
        }
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(frame.to_csv(index=False), encoding="utf-8")


def _benchmark_config(tmp_path: Path, input_path: Path) -> dict[str, object]:
    return {
        "benchmark_id": "benchmark-test",
        "output": {
            "base_dir": str(tmp_path / "reports" / "benchmarks"),
            "force_overwrite": True,
        },
        "training_spec": {
            "bundle_id": "unused",
            "data": {
                "year": 2023,
                "base_dir": str(tmp_path / "data"),
                "input_path": str(input_path),
                "sample_path": str(input_path),
                "use_sample_if_missing": False,
            },
            "artifacts": {
                "base_dir": str(tmp_path / "artifacts" / "models"),
                "force_overwrite": False,
                "notes": "benchmark test",
            },
            "features": [
                "age",
                "bmi",
                "smoker",
                "alcohol_servings_per_week",
                "exercise_minutes_per_week",
                "annual_aqi",
                "sex",
                "race_ethnicity",
                "has_healthcare_coverage",
                "has_personal_doctor",
                "cost_barrier_to_care",
                "last_checkup_within_year",
                "sleep_hours_per_night",
                "physical_health_days",
                "mental_health_days",
            ],
            "feature_contract": {
                "version": "brfss_v2",
                "scenario_editable_features": [
                    "age",
                    "bmi",
                    "smoker",
                    "alcohol_servings_per_week",
                    "exercise_minutes_per_week",
                    "annual_aqi",
                ],
                "adjustment_features": [
                    "sex",
                    "race_ethnicity",
                    "has_healthcare_coverage",
                    "has_personal_doctor",
                    "cost_barrier_to_care",
                    "last_checkup_within_year",
                    "sleep_hours_per_night",
                    "physical_health_days",
                    "mental_health_days",
                ],
                "context_features": [],
                "sample_weight_column": "survey_weight",
                "label_feature_exclusions": {
                    "heart_disease": ["physical_health_days"],
                    "chronic_lung_disease": ["physical_health_days"],
                },
            },
            "conditions": {
                "heart_disease": "label_heart_disease",
                "chronic_lung_disease": "label_chronic_lung_disease",
            },
            "training": {
                "random_state": 17,
                "test_size": 0.25,
                "calibration_method": "sigmoid",
                "calibration_cv": 3,
                "prediction_sample_rows": 1000,
            },
            "tuning": {
                "enabled": False,
                "metric": "average_precision",
                "n_trials": 1,
                "timeout_seconds": 30,
                "cv_folds": 3,
                "sample_size": 100,
            },
            "model": {
                "criterion": "gini",
                "class_weight": "balanced",
                "search_space": {
                    "max_depth": {"low": 2, "high": 4},
                    "min_samples_split": {"low": 5, "high": 20},
                    "min_samples_leaf": {"low": 2, "high": 10},
                    "max_leaf_nodes": {"low": 4, "high": 16},
                    "ccp_alpha": {"low": 0.00001, "high": 0.01},
                },
            },
        },
        "models": [
            {
                "model_id": "logistic_baseline",
                "kind": "logistic_regression",
                "params": {"max_iter": 500, "class_weight": "balanced"},
            },
            {
                "model_id": "tree_baseline",
                "kind": "decision_tree",
                "params": {"max_depth": 4, "min_samples_leaf": 5, "class_weight": "balanced"},
            },
        ],
        "ablations": [
            {
                "variant_id": "no_aqi",
                "display_name": "Drop AQI",
                "drop_features": ["annual_aqi"],
            }
        ],
        "subgroups": {"min_rows": 10},
        "calibration": {"bins": 5},
    }


def test_run_benchmark_writes_metrics_manifests_and_subgroups(tmp_path: Path) -> None:
    """Benchmark run should persist model-card-ready outputs."""
    input_path = tmp_path / "training.csv"
    _write_training_frame(input_path)

    result = run_benchmark(build_benchmark_spec(_benchmark_config(tmp_path, input_path)))

    assert result.manifest_path.exists()
    assert result.metrics_path.exists()
    assert result.calibration_path.exists()
    assert result.subgroup_metrics_path.exists()
    assert result.model_card_manifest_path.exists()

    metrics = json.loads(result.metrics_path.read_text(encoding="utf-8"))
    assert len(metrics) == 8
    assert {row["model_id"] for row in metrics} == {"logistic_baseline", "tree_baseline"}
    assert {row["variant_id"] for row in metrics} == {"all_features", "no_aqi"}
    assert all(row["rows_test"] == 60 for row in metrics)
    assert all(row["test_average_precision"] is not None for row in metrics)

    calibration = json.loads(result.calibration_path.read_text(encoding="utf-8"))
    assert calibration
    subgroups = pd.read_parquet(result.subgroup_metrics_path)
    assert {"model_id", "variant_id", "condition_id", "slice_dimension"}.issubset(subgroups.columns)
    assert "weighted_rows" in subgroups.columns
    assert "mean_predicted_probability_no_aqi" not in subgroups.columns
    model_cards = json.loads(result.model_card_manifest_path.read_text(encoding="utf-8"))
    assert len(model_cards["condition_cards"]) == 2


def test_default_benchmark_config_declares_context_ablation_variants() -> None:
    """Default benchmark config should include PR 20 context-aware ablations."""
    spec = load_benchmark_spec()

    assert "acs_poverty_percent" in spec.training_spec.feature_contract.context_features
    assert "svi_overall_percentile" in spec.training_spec.feature_contract.context_features
    assert "lightgbm" in {model.kind for model in spec.models}
    variant_ids = {ablation.variant_id for ablation in spec.ablations}
    assert {"no_context", "air_quality_only", "context_plus_air_quality"}.issubset(variant_ids)


def test_benchmark_includes_calibrated_hist_gradient_boosting_metadata(
    tmp_path: Path,
) -> None:
    """Histogram GBDT candidates should run through calibration and model cards."""
    input_path = tmp_path / "training.csv"
    _write_training_frame(input_path)
    config = _benchmark_config(tmp_path, input_path)
    models = cast(list[dict[str, object]], config["models"])
    config["models"] = [
        *models,
        {
            "model_id": "hgb_candidate",
            "kind": "hist_gradient_boosting",
            "class_imbalance_strategy": "class_weight_balanced",
            "params": {
                "max_iter": 12,
                "learning_rate": 0.08,
                "max_leaf_nodes": 7,
                "class_weight": "balanced",
            },
            "monotonic_constraints": {
                "age": 1,
                "bmi": 1,
                "exercise_minutes_per_week": -1,
                "annual_aqi": 1,
            },
        },
    ]

    result = run_benchmark(build_benchmark_spec(config))
    metrics = json.loads(result.metrics_path.read_text(encoding="utf-8"))
    hgb_rows = [row for row in metrics if row["model_id"] == "hgb_candidate"]

    assert hgb_rows
    assert {row["status"] for row in hgb_rows} == {"ok"}
    assert all(row["model_kind"] == "hist_gradient_boosting" for row in hgb_rows)
    assert all(row["test_average_precision"] is not None for row in hgb_rows)
    assert all(row["calibration_method"] == "sigmoid" for row in hgb_rows)
    assert all(row["class_imbalance_strategy"] == "class_weight_balanced" for row in hgb_rows)
    assert all(row["monotonic_constraints"]["age"] == 1 for row in hgb_rows)

    model_cards = json.loads(result.model_card_manifest_path.read_text(encoding="utf-8"))
    heart_card = next(
        card for card in model_cards["condition_cards"] if card["condition_id"] == "heart_disease"
    )
    assert heart_card["decision_tree_baseline_model_id"] == "tree_baseline"
    assert "best_delta_vs_decision_tree_baseline" in heart_card
    assert any(
        candidate["model_id"] == "hgb_candidate"
        and candidate["delta_vs_decision_tree_baseline"] is not None
        for candidate in heart_card["benchmark_candidates"]
    )


def test_benchmark_skips_optional_xgboost_when_dependency_unavailable(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """XGBoost should be optional and emit a clear skipped benchmark row."""
    input_path = tmp_path / "training.csv"
    _write_training_frame(input_path)
    config = _benchmark_config(tmp_path, input_path)
    models = cast(list[dict[str, object]], config["models"])
    config["models"] = [
        *models,
        {
            "model_id": "xgboost_candidate",
            "kind": "xgboost",
            "class_imbalance_strategy": "scale_pos_weight",
            "params": {"n_estimators": 4, "max_depth": 2, "learning_rate": 0.1},
            "monotonic_constraints": {"age": 1, "bmi": 1},
        },
    ]

    def _raise_missing_xgboost() -> object:
        raise modeling_module.OptionalModelDependencyError(
            "XGBoost support requires the optional train dependency."
        )

    monkeypatch.setattr(modeling_module, "_import_xgboost_classifier", _raise_missing_xgboost)

    result = run_benchmark(build_benchmark_spec(config))
    metrics = json.loads(result.metrics_path.read_text(encoding="utf-8"))
    xgb_rows = [row for row in metrics if row["model_id"] == "xgboost_candidate"]

    assert xgb_rows
    assert {row["status"] for row in xgb_rows} == {"skipped"}
    assert all(row["test_average_precision"] is None for row in xgb_rows)
    assert all("optional train dependency" in row["skip_reason"] for row in xgb_rows)
    calibration = json.loads(result.calibration_path.read_text(encoding="utf-8"))
    assert all(row["model_id"] != "xgboost_candidate" for row in calibration)


def test_benchmark_skips_optional_lightgbm_when_dependency_unavailable(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """LightGBM should be optional and emit a clear skipped benchmark row."""
    input_path = tmp_path / "training.csv"
    _write_training_frame(input_path)
    config = _benchmark_config(tmp_path, input_path)
    models = cast(list[dict[str, object]], config["models"])
    config["models"] = [
        *models,
        {
            "model_id": "lightgbm_candidate",
            "kind": "lightgbm",
            "class_imbalance_strategy": "class_weight_balanced",
            "params": {"n_estimators": 4, "max_depth": 2, "learning_rate": 0.1},
            "monotonic_constraints": {"age": 1, "bmi": 1},
        },
    ]

    def _raise_missing_lightgbm() -> object:
        raise modeling_module.OptionalModelDependencyError(
            "LightGBM support requires the optional train dependency."
        )

    monkeypatch.setattr(modeling_module, "_import_lightgbm_classifier", _raise_missing_lightgbm)

    result = run_benchmark(build_benchmark_spec(config))
    metrics = json.loads(result.metrics_path.read_text(encoding="utf-8"))
    lightgbm_rows = [row for row in metrics if row["model_id"] == "lightgbm_candidate"]

    assert lightgbm_rows
    assert {row["status"] for row in lightgbm_rows} == {"skipped"}
    assert all(row["test_average_precision"] is None for row in lightgbm_rows)
    assert all("optional train dependency" in row["skip_reason"] for row in lightgbm_rows)
    calibration = json.loads(result.calibration_path.read_text(encoding="utf-8"))
    assert all(row["model_id"] != "lightgbm_candidate" for row in calibration)


def test_benchmark_ablation_uses_condition_specific_feature_exclusions(tmp_path: Path) -> None:
    """Benchmark features should combine leakage exclusions with ablation rules."""
    input_path = tmp_path / "training.csv"
    _write_training_frame(input_path)

    result = run_benchmark(build_benchmark_spec(_benchmark_config(tmp_path, input_path)))
    metrics = json.loads(result.metrics_path.read_text(encoding="utf-8"))

    heart_all = next(
        row
        for row in metrics
        if row["condition_id"] == "heart_disease" and row["variant_id"] == "all_features"
    )
    heart_no_aqi = next(
        row
        for row in metrics
        if row["condition_id"] == "heart_disease" and row["variant_id"] == "no_aqi"
    )
    assert "physical_health_days" not in heart_all["features"]
    assert "annual_aqi" in heart_all["features"]
    assert "annual_aqi" not in heart_no_aqi["features"]
