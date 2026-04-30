"""Training pipeline integration tests."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd  # type: ignore[import-untyped]

from longevity_lab.api.schemas import FeatureProfile
from longevity_lab.artifacts.store import ArtifactStore
from longevity_lab.pipeline.modeling import (
    FeaturePreprocessor,
    build_training_spec,
    evaluate_bundle,
    evaluate_bundle_slices,
    make_hist_gradient_boosting_pipeline,
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
    sex = ["female" if idx % 2 == 0 else "male" for idx in range(rows)]
    race = [
        ["white_non_hispanic", "black_non_hispanic", "hispanic", "other_non_hispanic"][idx % 4]
        for idx in range(rows)
    ]
    has_coverage: list[bool | None] = [(idx % 11) != 0 for idx in range(rows)]
    has_coverage[3] = None
    has_doctor = [(idx % 7) != 0 for idx in range(rows)]
    cost_barrier = [(idx % 13) == 0 for idx in range(rows)]
    recent_checkup = [(idx % 5) != 0 for idx in range(rows)]
    sleep = [5 + (idx % 5) for idx in range(rows)]
    physical_health_days = [idx % 31 for idx in range(rows)]
    mental_health_days = [(idx * 2) % 31 for idx in range(rows)]
    survey_weight = [1.0 + (idx % 9) * 0.25 for idx in range(rows)]
    frame = pd.DataFrame(
        {
            "year": [2023] * rows,
            "state_fips": ["13"] * rows,
            "sex": sex,
            "race_ethnicity": race,
            "age": age,
            "bmi": bmi,
            "smoker": smoker,
            "alcohol_servings_per_week": alcohol,
            "exercise_minutes_per_week": exercise,
            "annual_aqi": annual_aqi,
            "has_healthcare_coverage": has_coverage,
            "has_personal_doctor": has_doctor,
            "cost_barrier_to_care": cost_barrier,
            "last_checkup_within_year": recent_checkup,
            "sleep_hours_per_night": sleep,
            "physical_health_days": physical_health_days,
            "mental_health_days": mental_health_days,
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
            "survey_weight": survey_weight,
        }
    )
    frame.loc[0, "bmi"] = None
    frame.loc[1, "annual_aqi"] = None
    frame.loc[2, "race_ethnicity"] = None
    frame.loc[4, "sleep_hours_per_night"] = None
    path.write_text(frame.to_csv(index=False), encoding="utf-8")


def _base_raw_cfg(
    *,
    tmp_path: Path,
    input_path: Path,
    bundle_id: str,
    features: list[str] | None = None,
) -> dict[str, object]:
    return {
        "bundle_id": bundle_id,
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
        "features": features
        or [
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
            "enabled": False,
            "metric": "average_precision",
            "n_trials": 1,
            "timeout_seconds": 30,
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


BRFSS_V2_FEATURES = [
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
]

BRFSS_V2_CONTRACT = {
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
        "stroke": ["physical_health_days"],
        "depression": ["mental_health_days"],
        "diabetes": ["physical_health_days"],
    },
}


def test_feature_preprocessor_encodes_v2_categorical_covariates() -> None:
    """Feature preprocessing should one-hot encode categorical adjustment covariates."""
    frame = pd.DataFrame(
        {
            "age": [40, 60],
            "sex": ["female", "male"],
            "race_ethnicity": ["hispanic", None],
            "has_healthcare_coverage": [True, "False"],
        }
    )
    preprocessor = FeaturePreprocessor(
        feature_names=("age", "sex", "race_ethnicity", "has_healthcare_coverage")
    )
    transformed = preprocessor.fit_transform(frame)

    assert "age" in transformed.columns
    assert "has_healthcare_coverage" in transformed.columns
    assert "sex_female" in transformed.columns
    assert "sex_male" in transformed.columns
    assert "race_ethnicity_hispanic" in transformed.columns
    assert "race_ethnicity_missing" in transformed.columns
    assert transformed.loc[0, "has_healthcare_coverage"] == 1.0
    assert transformed.loc[1, "has_healthcare_coverage"] == 0.0


def test_hist_gradient_boosting_pipeline_applies_monotonic_constraints() -> None:
    """HGB pipelines should map raw-feature monotonic constraints after preprocessing."""
    frame = pd.DataFrame(
        {
            "age": [25, 45, 65, 75, 35, 55],
            "bmi": [22.0, 26.0, 34.0, 36.0, 24.0, 31.0],
            "exercise_minutes_per_week": [220, 150, 20, 0, 180, 40],
            "sex": ["female", "male", "female", "male", "female", "male"],
        }
    )
    labels = pd.Series([0, 0, 1, 1, 0, 1])
    pipeline = make_hist_gradient_boosting_pipeline(
        feature_names=("age", "bmi", "exercise_minutes_per_week", "sex"),
        params={"max_iter": 5, "min_samples_leaf": 2, "class_weight": "balanced"},
        monotonic_constraints={"age": 1, "bmi": 1, "exercise_minutes_per_week": -1},
        random_state=3,
    )

    pipeline.fit(frame, labels, sample_weight=pd.Series([1.0, 1.0, 2.0, 2.0, 1.0, 2.0]))

    transformed_features = list(pipeline.named_steps["preprocess"].get_feature_names_out())
    model = pipeline.named_steps["model"]
    assert list(model.monotonic_cst) == [  # type: ignore[attr-defined]
        1 if name in {"age", "bmi"} else -1 if name == "exercise_minutes_per_week" else 0
        for name in transformed_features
    ]
    probabilities = pipeline.predict_proba(frame)
    assert probabilities.shape == (6, 2)


def test_train_bundle_writes_artifacts_and_supports_engine(tmp_path: Path) -> None:
    """Training should write a loadable artifact bundle with per-condition outputs."""
    input_path = tmp_path / "training.csv"
    _write_training_frame(input_path)

    raw_cfg = _base_raw_cfg(tmp_path=tmp_path, input_path=input_path, bundle_id="bundle-test")
    raw_cfg["tuning"] = {
        "enabled": True,
        "metric": "average_precision",
        "n_trials": 2,
        "timeout_seconds": 60,
        "cv_folds": 3,
        "sample_size": 250,
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


def test_train_bundle_applies_brfss_v2_feature_contract(tmp_path: Path) -> None:
    """Training should record v2 roles, use survey weights, and apply leakage exclusions."""
    input_path = tmp_path / "training.csv"
    _write_training_frame(input_path)

    raw_cfg = _base_raw_cfg(
        tmp_path=tmp_path,
        input_path=input_path,
        bundle_id="bundle-v2",
        features=BRFSS_V2_FEATURES,
    )
    raw_cfg["feature_contract"] = BRFSS_V2_CONTRACT
    result = train_bundle(build_training_spec(raw_cfg))

    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["features"] == BRFSS_V2_FEATURES

    summary = json.loads(result.training_summary_path.read_text(encoding="utf-8"))
    assert summary["feature_contract"]["version"] == "brfss_v2"
    assert summary["feature_contract"]["sample_weight_column"] == "survey_weight"

    by_condition = {item["condition_id"]: item for item in summary["conditions"]}
    assert "physical_health_days" not in by_condition["heart_disease"]["features"]
    assert "mental_health_days" not in by_condition["depression"]["features"]
    assert "mental_health_days" in by_condition["heart_disease"]["features"]
    assert "physical_health_days" in by_condition["depression"]["features"]

    metrics_path = result.bundle_dir / "heart_disease_metrics.json"
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    assert metrics["sample_weight_column"] == "survey_weight"
    assert metrics["weighted_rows_train"] > metrics["rows_train"]

    predictions = pd.read_parquet(result.bundle_dir / "heart_disease_predictions.parquet")
    assert "survey_weight" in predictions.columns

    engine = ArtifactScenarioEngine(
        store=ArtifactStore(tmp_path / "artifacts" / "models"),
        bundle_id="bundle-v2",
    )
    scores = engine.evaluate(
        FeatureProfile(
            age=67,
            bmi=35.0,
            smoker=True,
            alcohol_servings_per_week=18,
            exercise_minutes_per_week=10,
            annual_aqi=130,
        )
    )
    assert len(scores) == 5
    assert all(0.0 <= score.probability <= 1.0 for score in scores)


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
