"""Training pipeline integration tests."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd  # type: ignore[import-untyped]

from longevity_lab.api.schemas import FeatureProfile
from longevity_lab.artifacts.store import ArtifactStore
from longevity_lab.pipeline.modeling import (
    build_training_spec,
    evaluate_bundle,
    evaluate_bundle_slices,
    train_bundle,
)
from longevity_lab.services.artifact_engine import ArtifactScenarioEngine


def _write_training_frame(path: Path, *, rows: int = 400) -> None:
    age = [25 + (idx % 55) for idx in range(rows)]
    bmi = [20.0 + (idx % 18) * 0.8 for idx in range(rows)]
    smoker = [(idx % 5) == 0 for idx in range(rows)]
    alcohol = [idx % 21 for idx in range(rows)]
    exercise = [30 + (idx % 12) * 20 for idx in range(rows)]
    annual_aqi = [40 + (idx % 9) * 12 for idx in range(rows)]
    frame = pd.DataFrame(
        {
            "year": [2023] * rows,
            "state_fips": ["13"] * rows,
            "age": age,
            "bmi": bmi,
            "smoker": smoker,
            "alcohol_servings_per_week": alcohol,
            "exercise_minutes_per_week": exercise,
            "annual_aqi": annual_aqi,
            "label_heart_disease": [
                int(item_age > 60 or item_bmi > 32 or item_smoker)
                for item_age, item_bmi, item_smoker in zip(age, bmi, smoker, strict=True)
            ],
            "label_chronic_lung_disease": [
                int(item_smoker or item_aqi > 110)
                for item_smoker, item_aqi in zip(smoker, annual_aqi, strict=True)
            ],
            "label_stroke": [
                int(item_age > 70 or item_aqi > 120)
                for item_age, item_aqi in zip(age, annual_aqi, strict=True)
            ],
            "label_depression": [
                int(item_exercise < 90 or item_alcohol > 12)
                for item_exercise, item_alcohol in zip(exercise, alcohol, strict=True)
            ],
            "label_diabetes": [
                int(item_bmi > 31 or item_age > 58)
                for item_bmi, item_age in zip(bmi, age, strict=True)
            ],
            "survey_weight": [1.0] * rows,
        }
    )
    frame.loc[0, "bmi"] = None
    frame.loc[1, "annual_aqi"] = None
    path.write_text(frame.to_csv(index=False), encoding="utf-8")


def test_train_bundle_writes_artifacts_and_supports_engine(tmp_path: Path) -> None:
    """Training should write a loadable artifact bundle with per-condition outputs."""
    input_path = tmp_path / "training.csv"
    _write_training_frame(input_path)

    raw_cfg = {
        "bundle_id": "bundle-test",
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
            "notes": "test bundle",
        },
        "features": [
            "age",
            "bmi",
            "smoker",
            "alcohol_servings_per_week",
            "exercise_minutes_per_week",
            "annual_aqi",
        ],
        "conditions": {
            "heart_disease": "label_heart_disease",
            "chronic_lung_disease": "label_chronic_lung_disease",
            "stroke": "label_stroke",
            "depression": "label_depression",
            "diabetes": "label_diabetes",
        },
        "training": {
            "random_state": 7,
            "test_size": 0.2,
            "calibration_method": "sigmoid",
            "calibration_cv": 3,
            "prediction_sample_rows": 2000,
        },
        "tuning": {
            "enabled": True,
            "metric": "average_precision",
            "n_trials": 2,
            "timeout_seconds": 60,
            "cv_folds": 3,
            "sample_size": 250,
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
    }
    spec = build_training_spec(raw_cfg)
    result = train_bundle(spec)

    assert result.bundle_dir.exists()
    assert result.manifest_path.exists()
    assert result.training_summary_path.exists()
    summary = json.loads(result.training_summary_path.read_text(encoding="utf-8"))
    assert len(summary["conditions"]) == 5

    metrics_files = list(result.bundle_dir.glob("*_metrics.json"))
    prediction_files = list(result.bundle_dir.glob("*_predictions.parquet"))
    assert len(metrics_files) == 5
    assert len(prediction_files) == 5

    engine = ArtifactScenarioEngine(
        store=ArtifactStore(tmp_path / "artifacts" / "models"),
        bundle_id="bundle-test",
    )
    scores = engine.evaluate(
        FeatureProfile(
            age=67,
            bmi=33.0,
            smoker=True,
            alcohol_servings_per_week=12,
            exercise_minutes_per_week=40,
            annual_aqi=120,
        )
    )
    assert len(scores) == 5
    assert any(score.key_drivers for score in scores)


def test_evaluate_bundle_returns_condition_summary(tmp_path: Path) -> None:
    """evaluate_bundle should aggregate calibrated and ablation metrics."""
    input_path = tmp_path / "training.csv"
    _write_training_frame(input_path)

    raw_cfg = {
        "bundle_id": "bundle-eval",
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
            "notes": "test bundle",
        },
        "features": [
            "age",
            "bmi",
            "smoker",
            "alcohol_servings_per_week",
            "exercise_minutes_per_week",
            "annual_aqi",
        ],
        "conditions": {
            "heart_disease": "label_heart_disease",
            "chronic_lung_disease": "label_chronic_lung_disease",
            "stroke": "label_stroke",
            "depression": "label_depression",
            "diabetes": "label_diabetes",
        },
        "training": {
            "random_state": 11,
            "test_size": 0.2,
            "calibration_method": "sigmoid",
            "calibration_cv": 3,
            "prediction_sample_rows": 2000,
        },
        "tuning": {
            "enabled": False,
            "metric": "average_precision",
            "n_trials": 1,
            "timeout_seconds": 30,
            "cv_folds": 3,
            "sample_size": 200,
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
    }
    result = train_bundle(build_training_spec(raw_cfg))
    summary = evaluate_bundle(result.bundle_dir)
    assert set(summary.columns) == {
        "condition_id",
        "test_average_precision",
        "test_roc_auc",
        "test_brier_score",
        "test_average_precision_no_aqi",
        "positive_rate",
    }
    assert len(summary) == 5


def test_evaluate_bundle_slices_returns_group_metrics(tmp_path: Path) -> None:
    """Slice evaluation should export subgroup metrics for report-ready analysis."""
    input_path = tmp_path / "training.csv"
    _write_training_frame(input_path, rows=800)

    raw_cfg = {
        "bundle_id": "bundle-slices",
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
            "notes": "test bundle",
        },
        "features": [
            "age",
            "bmi",
            "smoker",
            "alcohol_servings_per_week",
            "exercise_minutes_per_week",
            "annual_aqi",
        ],
        "conditions": {
            "heart_disease": "label_heart_disease",
            "chronic_lung_disease": "label_chronic_lung_disease",
            "stroke": "label_stroke",
            "depression": "label_depression",
            "diabetes": "label_diabetes",
        },
        "training": {
            "random_state": 13,
            "test_size": 0.2,
            "calibration_method": "sigmoid",
            "calibration_cv": 3,
            "prediction_sample_rows": 5000,
        },
        "tuning": {
            "enabled": False,
            "metric": "average_precision",
            "n_trials": 1,
            "timeout_seconds": 30,
            "cv_folds": 3,
            "sample_size": 400,
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
    }

    result = train_bundle(build_training_spec(raw_cfg))
    slices = evaluate_bundle_slices(result.bundle_dir, min_rows=10)

    assert set(slices.columns) == {
        "condition_id",
        "slice_dimension",
        "slice_value",
        "n_rows",
        "n_positive",
        "n_negative",
        "positive_rate",
        "mean_predicted_probability",
        "mean_predicted_probability_uncalibrated",
        "mean_predicted_probability_no_aqi",
        "calibration_gap",
        "average_precision",
        "roc_auc",
        "brier_score",
        "status",
    }
    assert set(slices["slice_dimension"]) == {
        "age_band",
        "bmi_band",
        "smoker_status",
        "aqi_tier",
        "exercise_tier",
    }
    assert {"ok", "too_small", "single_class"} >= set(slices["status"])
    assert (slices["status"] == "ok").any()
