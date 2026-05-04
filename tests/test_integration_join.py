"""Tests for BRFSS + EPA integration join logic."""

import pandas as pd  # type: ignore[import-untyped]
import pytest

from longevity_lab.pipeline.build_integrated_tables import integrate_brfss_epa


def _with_v2_covariates(payload: dict[str, list[object]]) -> dict[str, list[object]]:
    """Add required BRFSS v2 covariates to a test payload."""
    rows = len(payload["year"])
    payload.update(
        {
            "sex": ["female"] * rows,
            "race_ethnicity": ["white_non_hispanic"] * rows,
            "has_healthcare_coverage": [True] * rows,
            "has_personal_doctor": [True] * rows,
            "cost_barrier_to_care": [False] * rows,
            "last_checkup_within_year": [True] * rows,
            "sleep_hours_per_night": [7] * rows,
            "physical_health_days": [0] * rows,
            "mental_health_days": [0] * rows,
            "label_asthma": [0] * rows,
            "label_kidney_disease": [0] * rows,
            "label_arthritis": [0] * rows,
        }
    )
    return payload


def test_integrate_brfss_epa_happy_path() -> None:
    """Join should attach annual_aqi by (year, state_fips)."""
    brfss = pd.DataFrame(
        _with_v2_covariates(
            {
                "year": [2023, 2023],
                "state_fips": ["01", "06"],
                "age": [21, 42],
                "bmi": [25.0, 30.1],
                "smoker": [True, False],
                "alcohol_servings_per_week": [10, 0],
                "exercise_minutes_per_week": [150, 200],
                "label_heart_disease": [0, 1],
                "label_chronic_lung_disease": [0, 0],
                "label_stroke": [0, 0],
                "label_depression": [0, 1],
                "label_diabetes": [0, 0],
                "survey_weight": [1.0, 2.0],
            }
        )
    )
    epa = pd.DataFrame(
        {
            "year": [2023, 2023],
            "state_fips": ["01", "06"],
            "annual_aqi": [45, 60],
        }
    )
    integrated = integrate_brfss_epa(brfss, epa, allow_missing_aqi=False)
    assert integrated["annual_aqi"].tolist() == [45, 60]


def test_integrate_brfss_epa_preserves_v2_brfss_covariates() -> None:
    """The integrated training table should carry non-editable BRFSS v2 covariates."""
    brfss = pd.DataFrame(
        {
            "year": [2023],
            "state_fips": ["01"],
            "sex": ["female"],
            "race_ethnicity": ["white_non_hispanic"],
            "age": [45],
            "bmi": [27.5],
            "smoker": [False],
            "alcohol_servings_per_week": [1],
            "exercise_minutes_per_week": [150],
            "has_healthcare_coverage": [True],
            "has_personal_doctor": [True],
            "cost_barrier_to_care": [False],
            "last_checkup_within_year": [True],
            "sleep_hours_per_night": [None],
            "physical_health_days": [0],
            "mental_health_days": [2],
            "label_heart_disease": [0],
            "label_chronic_lung_disease": [0],
            "label_asthma": [0],
            "label_stroke": [0],
            "label_depression": [0],
            "label_diabetes": [0],
            "label_kidney_disease": [0],
            "label_arthritis": [0],
            "survey_weight": [1.0],
        }
    )
    epa = pd.DataFrame({"year": [2023], "state_fips": ["01"], "annual_aqi": [50]})

    integrated = integrate_brfss_epa(brfss, epa, allow_missing_aqi=False)

    assert integrated.loc[0, "sex"] == "female"
    assert integrated.loc[0, "race_ethnicity"] == "white_non_hispanic"
    assert bool(integrated.loc[0, "has_healthcare_coverage"]) is True
    assert integrated.loc[0, "physical_health_days"] == 0
    assert integrated.loc[0, "mental_health_days"] == 2


def test_integrate_brfss_epa_rejects_missing_aqi() -> None:
    """Join should raise if annual_aqi is missing unless allowed."""
    brfss = pd.DataFrame(
        _with_v2_covariates(
            {
                "year": [2023],
                "state_fips": ["78"],
                "age": [67],
                "bmi": [26.0],
                "smoker": [False],
                "alcohol_servings_per_week": [0],
                "exercise_minutes_per_week": [0],
                "label_heart_disease": [0],
                "label_chronic_lung_disease": [0],
                "label_stroke": [0],
                "label_depression": [0],
                "label_diabetes": [0],
                "survey_weight": [1.0],
            }
        )
    )
    epa = pd.DataFrame({"year": [2023], "state_fips": ["01"], "annual_aqi": [50]})
    with pytest.raises(ValueError, match="Missing annual_aqi"):
        integrate_brfss_epa(brfss, epa, allow_missing_aqi=False)
    integrated = integrate_brfss_epa(brfss, epa, allow_missing_aqi=True)
    assert integrated["annual_aqi"].isna().all()


def test_integrate_brfss_epa_allows_expected_missing_territory() -> None:
    """Documented EPA gaps for supported BRFSS territories should not fail by default."""
    brfss = pd.DataFrame(
        _with_v2_covariates(
            {
                "year": [2023],
                "state_fips": ["66"],
                "age": [45],
                "bmi": [27.5],
                "smoker": [False],
                "alcohol_servings_per_week": [1],
                "exercise_minutes_per_week": [150],
                "label_heart_disease": [0],
                "label_chronic_lung_disease": [0],
                "label_stroke": [0],
                "label_depression": [0],
                "label_diabetes": [0],
                "survey_weight": [1.0],
            }
        )
    )
    epa = pd.DataFrame({"year": [2023], "state_fips": ["01"], "annual_aqi": [50]})

    integrated = integrate_brfss_epa(brfss, epa, allow_missing_aqi=False)
    assert integrated["annual_aqi"].isna().all()


def test_integrate_brfss_epa_rejects_stale_v1_brfss_table() -> None:
    """The v2 integrated table should fail early if required BRFSS covariates are absent."""
    brfss = pd.DataFrame(
        {
            "year": [2023],
            "state_fips": ["01"],
            "age": [45],
            "bmi": [27.5],
            "smoker": [False],
            "alcohol_servings_per_week": [1],
            "exercise_minutes_per_week": [150],
            "label_heart_disease": [0],
            "label_chronic_lung_disease": [0],
            "label_asthma": [0],
            "label_stroke": [0],
            "label_depression": [0],
            "label_diabetes": [0],
            "label_kidney_disease": [0],
            "label_arthritis": [0],
            "survey_weight": [1.0],
        }
    )
    epa = pd.DataFrame({"year": [2023], "state_fips": ["01"], "annual_aqi": [50]})

    with pytest.raises(ValueError, match="sex"):
        integrate_brfss_epa(brfss, epa, allow_missing_aqi=False)


def test_integrate_brfss_epa_includes_quality_gated_pollutant_features() -> None:
    """Optional pollutant columns should join only when state-year quality flags pass."""
    brfss = pd.DataFrame(
        _with_v2_covariates(
            {
                "year": [2023, 2023],
                "state_fips": ["06", "12"],
                "age": [42, 67],
                "bmi": [30.1, 26.0],
                "smoker": [False, False],
                "alcohol_servings_per_week": [0, 0],
                "exercise_minutes_per_week": [200, 0],
                "label_heart_disease": [1, 0],
                "label_chronic_lung_disease": [0, 0],
                "label_stroke": [0, 0],
                "label_depression": [1, 0],
                "label_diabetes": [0, 0],
                "survey_weight": [2.0, 1.0],
            }
        )
    )
    epa = pd.DataFrame(
        {
            "year": [2023, 2023],
            "state_fips": ["06", "12"],
            "annual_aqi": [60, 45],
            "pm25_mean": [8.5, 12.0],
            "pm25_monitor_count": [2, 1],
            "pm25_observation_percent": [90.0, 40.0],
            "pm25_observation_complete": [True, False],
            "ozone_mean": [0.041, 0.050],
            "ozone_monitor_count": [1, 1],
            "ozone_observation_percent": [88.0, 30.0],
            "ozone_observation_complete": [True, False],
        }
    )

    integrated = integrate_brfss_epa(brfss, epa, allow_missing_aqi=False)

    assert "pm25_mean" in integrated.columns
    assert "ozone_mean" in integrated.columns
    assert integrated.loc[integrated["state_fips"] == "06", "pm25_mean"].iloc[0] == 8.5
    assert integrated.loc[integrated["state_fips"] == "06", "ozone_mean"].iloc[0] == 0.041
    assert pd.isna(integrated.loc[integrated["state_fips"] == "12", "pm25_mean"].iloc[0])
    assert pd.isna(integrated.loc[integrated["state_fips"] == "12", "ozone_mean"].iloc[0])
