"""Tests for BRFSS + EPA integration join logic."""

import pandas as pd  # type: ignore[import-untyped]
import pytest

from longevity_lab.pipeline.build_integrated_tables import integrate_brfss_epa


def test_integrate_brfss_epa_happy_path() -> None:
    """Join should attach annual_aqi by (year, state_fips)."""
    brfss = pd.DataFrame(
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
    epa = pd.DataFrame(
        {
            "year": [2023, 2023],
            "state_fips": ["01", "06"],
            "annual_aqi": [45, 60],
        }
    )
    integrated = integrate_brfss_epa(brfss, epa, allow_missing_aqi=False)
    assert integrated["annual_aqi"].tolist() == [45, 60]


def test_integrate_brfss_epa_rejects_missing_aqi() -> None:
    """Join should raise if annual_aqi is missing unless allowed."""
    brfss = pd.DataFrame(
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
    epa = pd.DataFrame({"year": [2023], "state_fips": ["01"], "annual_aqi": [50]})
    with pytest.raises(ValueError, match="Missing annual_aqi"):
        integrate_brfss_epa(brfss, epa, allow_missing_aqi=False)
    integrated = integrate_brfss_epa(brfss, epa, allow_missing_aqi=True)
    assert integrated["annual_aqi"].isna().all()


def test_integrate_brfss_epa_allows_expected_missing_territory() -> None:
    """Documented EPA gaps for supported BRFSS territories should not fail by default."""
    brfss = pd.DataFrame(
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
    epa = pd.DataFrame({"year": [2023], "state_fips": ["01"], "annual_aqi": [50]})

    integrated = integrate_brfss_epa(brfss, epa, allow_missing_aqi=False)
    assert integrated["annual_aqi"].isna().all()
