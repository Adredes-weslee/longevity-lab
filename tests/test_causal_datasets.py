"""Tests for causal workbench dataset preparation."""

from __future__ import annotations

from pathlib import Path

import pandas as pd  # type: ignore[import-untyped]
import pytest

from longevity_lab.causal.datasets import (
    load_smoking_lung_config,
    prepare_smoking_lung_dataset,
)


def _write_smoking_frame(path: Path) -> None:
    """Write a tiny integrated person-year table for causal tests."""
    frame = pd.DataFrame(
        {
            "year": [2023, 2023, 2023, 2023, 2023, 2023],
            "state_fips": ["01", "01", "06", "06", "12", "12"],
            "sex": ["female", "male", "female", "male", "female", "male"],
            "race_ethnicity": [
                "white_non_hispanic",
                "black_non_hispanic",
                "hispanic",
                "white_non_hispanic",
                "hispanic",
                "other_non_hispanic",
            ],
            "age": [45, 52, 60, 63, 17, 70],
            "bmi": [24.5, 29.1, 31.0, 22.8, 27.3, 28.4],
            "smoker": [True, False, None, True, False, False],
            "alcohol_servings_per_week": [1, 3, 8, 2, 0, 4],
            "exercise_minutes_per_week": [160, 90, 30, 200, 100, 40],
            "annual_aqi": [55, 61, 70, 64, 50, 84],
            "has_healthcare_coverage": [True, True, False, True, True, None],
            "has_personal_doctor": [True, True, False, True, False, True],
            "cost_barrier_to_care": [False, False, True, False, False, True],
            "last_checkup_within_year": [True, True, False, True, True, False],
            "sleep_hours_per_night": [7, 6, 5, 8, 7, 6],
            "physical_health_days": [4, 1, 12, 2, 0, 20],
            "mental_health_days": [0, 2, 5, 1, 0, 7],
            "label_chronic_lung_disease": [1, 0, 1, None, 0, 1],
            "survey_weight": [2.0, 1.0, 3.0, 4.0, 1.0, None],
        }
    )
    frame.to_parquet(path, index=False)


def test_smoking_lung_config_matches_pr11_question() -> None:
    """Default PR12 config should implement the smoking-to-lung-disease question."""
    config = load_smoking_lung_config()

    assert config.question_id == "smoking_chronic_lung_disease"
    assert config.source_question_registry.name == "questions.yaml"
    assert config.treatment_contrast == "current smoker versus not current smoker"
    assert config.outcome_timing == "prevalent diagnosed condition, not incident disease"
    assert config.treatment_column == "smoker"
    assert config.outcome_column == "label_chronic_lung_disease"
    assert config.sample_weight_column == "survey_weight"
    assert "age" in config.adjustment_columns
    assert "physical_health_days" not in config.adjustment_columns
    assert "physical_health_days" in config.excluded_columns
    assert config.output_dir.as_posix().endswith("data/processed/reports/causal/smoking_lung")
    assert config.negative_control_outcomes == (
        "sex_at_birth_if_available",
        "race_ethnicity_if_available",
        "adult_height_if_available",
        "interview_month_if_available",
    )
    assert "dowhy_placebo_subset_random_common_cause_refutations" in config.sensitivity_checks
    assert config.base_dir.is_absolute()
    assert config.sample_path is not None
    assert config.sample_path.is_absolute()


def test_prepare_smoking_lung_dataset_tracks_exclusions_and_roles(tmp_path: Path) -> None:
    """Dataset preparation should coerce roles and preserve transparent exclusion counts."""
    input_path = tmp_path / "integrated_person_year.parquet"
    _write_smoking_frame(input_path)
    config = load_smoking_lung_config()

    prepared = prepare_smoking_lung_dataset(input_path=input_path, config=config)

    assert prepared.source_path == input_path
    assert prepared.question_id == "smoking_chronic_lung_disease"
    assert prepared.input_rows == 6
    assert prepared.analysis_rows == 3
    assert prepared.exclusions == {
        "missing_treatment": 1,
        "missing_outcome": 1,
        "outside_adult_age_range": 1,
    }
    assert prepared.frame[config.treatment_column].tolist() == [1, 0, 0]
    assert prepared.frame[config.outcome_column].tolist() == [1, 0, 1]
    assert prepared.frame[config.sample_weight_column].isna().sum() == 0
    assert prepared.frame[config.sample_weight_column].iloc[-1] == pytest.approx(1.5)
    assert "physical_health_days" not in prepared.frame.columns
    assert set(config.adjustment_columns).issubset(prepared.frame.columns)


def test_prepare_smoking_lung_dataset_rejects_missing_required_columns(tmp_path: Path) -> None:
    """Preparation should fail early when the processed table is not the v2 contract."""
    input_path = tmp_path / "bad.csv"
    pd.DataFrame({"smoker": [True], "label_chronic_lung_disease": [1]}).to_csv(
        input_path,
        index=False,
    )

    with pytest.raises(ValueError, match="Missing required columns"):
        prepare_smoking_lung_dataset(input_path=input_path, config=load_smoking_lung_config())


def test_smoking_lung_config_paths_are_repo_root_relative(monkeypatch: pytest.MonkeyPatch) -> None:
    """Relative paths in the default config should not depend on the current directory."""
    monkeypatch.chdir(Path(__file__).parent)

    config = load_smoking_lung_config(Path("conf/causal/smoking_lung.yaml"))

    assert config.base_dir == Path(__file__).resolve().parents[1] / "data"
    assert config.sample_path is not None
    assert config.sample_path.parent.name == "sample"
