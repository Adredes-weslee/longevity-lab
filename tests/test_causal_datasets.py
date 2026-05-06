"""Tests for causal workbench dataset preparation."""

from __future__ import annotations

from pathlib import Path

import pandas as pd  # type: ignore[import-untyped]
import pytest

from longevity_lab.causal.datasets import (
    load_causal_config_for_question,
    load_smoking_lung_config,
    prepare_causal_dataset,
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


def test_prepare_activity_diabetes_dataset_derives_threshold_treatment(tmp_path: Path) -> None:
    """Activity question should derive the guidance indicator without adjusting for BMI."""
    input_path = tmp_path / "integrated_person_year.parquet"
    _write_multi_question_frame(input_path)
    config = load_causal_config_for_question("activity_diabetes")

    prepared = prepare_causal_dataset(input_path=input_path, config=config)

    assert prepared.question_id == "physical_activity_diabetes"
    assert config.treatment_column == "meets_physical_activity_guidance"
    assert prepared.frame[config.treatment_column].tolist() == [0, 1, 1, 0, 1]
    assert "bmi" not in config.adjustment_columns
    assert "bmi_in_primary_total_effect_model" in config.excluded_columns
    assert prepared.exclusions == {"outside_adult_age_range": 1}


def test_prepare_bmi_diabetes_dataset_excludes_noncontrast_bmi(tmp_path: Path) -> None:
    """BMI question should keep only normal-range and obesity-range respondents."""
    input_path = tmp_path / "integrated_person_year.parquet"
    _write_multi_question_frame(input_path)
    config = load_causal_config_for_question("bmi_diabetes")

    prepared = prepare_causal_dataset(input_path=input_path, config=config)

    assert prepared.question_id == "bmi_diabetes"
    assert prepared.frame[config.treatment_column].tolist() == [0, 1, 1, 0]
    assert prepared.exclusions == {
        "outside_bmi_obesity_vs_normal_contrast": 1,
        "outside_adult_age_range": 1,
    }


def test_prepare_alcohol_depression_dataset_derives_sex_specific_heavy_use(
    tmp_path: Path,
) -> None:
    """Alcohol question should apply fixed sex-specific heavy-use thresholds."""
    input_path = tmp_path / "integrated_person_year.parquet"
    _write_multi_question_frame(input_path)
    config = load_causal_config_for_question("alcohol_depression")

    prepared = prepare_causal_dataset(input_path=input_path, config=config)

    assert prepared.question_id == "alcohol_depression"
    assert prepared.frame[config.treatment_column].tolist() == [0, 1, 0, 1, 0]
    assert config.outcome_column == "label_depression"
    assert "mental_health_days" not in config.adjustment_columns
    assert "mental_health_days" in config.excluded_columns


@pytest.mark.parametrize(
    ("question", "downstream_column"),
    [
        ("smoking_lung", "physical_health_days"),
        ("activity_diabetes", "physical_health_days"),
        ("bmi_diabetes", "physical_health_days"),
        ("alcohol_depression", "mental_health_days"),
    ],
)
def test_prepare_causal_dataset_does_not_require_excluded_downstream_fields(
    tmp_path: Path,
    question: str,
    downstream_column: str,
) -> None:
    """De-leaked causal tables may omit excluded symptom/downstream fields."""
    input_path = tmp_path / "integrated_person_year.parquet"
    _write_multi_question_frame(input_path)
    frame = pd.read_parquet(input_path)
    frame["label_chronic_lung_disease"] = [1, 0, 1, 0, 1, 1]
    frame = frame.drop(columns=[downstream_column])
    frame.to_parquet(input_path, index=False)

    config = load_causal_config_for_question(question)
    prepared = prepare_causal_dataset(input_path=input_path, config=config)

    assert downstream_column not in config.required_columns
    assert downstream_column not in prepared.frame.columns


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


def _write_multi_question_frame(path: Path) -> None:
    """Write deterministic integrated rows for non-smoking causal questions."""
    frame = pd.DataFrame(
        {
            "year": [2023, 2023, 2023, 2023, 2023, 2023],
            "state_fips": ["01", "01", "06", "06", "12", "12"],
            "sex": ["female", "female", "male", "male", "female", "male"],
            "race_ethnicity": [
                "white_non_hispanic",
                "black_non_hispanic",
                "hispanic",
                "white_non_hispanic",
                "hispanic",
                "other_non_hispanic",
            ],
            "age": [45, 52, 60, 63, 70, 17],
            "bmi": [23.0, 31.0, 35.0, 22.0, 27.5, 40.0],
            "smoker": [True, False, False, True, False, False],
            "alcohol_servings_per_week": [7, 8, 14, 15, 0, 4],
            "exercise_minutes_per_week": [120, 150, 240, 90, 180, 30],
            "annual_aqi": [55, 61, 70, 64, 50, 84],
            "has_healthcare_coverage": [True, True, False, True, True, True],
            "has_personal_doctor": [True, True, False, True, False, True],
            "cost_barrier_to_care": [False, False, True, False, False, True],
            "last_checkup_within_year": [True, True, False, True, True, False],
            "physical_health_days": [4, 1, 12, 2, 0, 20],
            "mental_health_days": [0, 2, 5, 1, 0, 7],
            "label_diabetes": [0, 1, 1, 0, 1, 1],
            "label_depression": [0, 1, 0, 1, 0, 1],
            "survey_weight": [2.0, 1.0, 3.0, 4.0, 1.0, None],
        }
    )
    frame.to_parquet(path, index=False)
