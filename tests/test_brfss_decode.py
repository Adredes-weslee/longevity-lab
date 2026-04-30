"""Unit tests for BRFSS decode logic (no network, no large files)."""

import pandas as pd  # type: ignore[import-untyped]

from longevity_lab.pipeline.build_brfss_tables import (
    BRFSS_ADJUSTMENT_FEATURES,
    BRFSS_LABEL_FEATURE_EXCLUSIONS,
    BRFSS_SCENARIO_FEATURES,
    decode_brfss_person,
)


def test_decode_brfss_person_happy_path() -> None:
    """decode_brfss_person should map v2 features/labels and missing codes."""
    raw = pd.DataFrame(
        {
            "_STATE": [1, 12],
            "SEXVAR": [1, 2],
            "_IMPRACE": [1, 5],
            "PRIMINS1": [1, 88],
            "PERSDOC3": [1, 3],
            "MEDCOST1": [1, 2],
            "CHECKUP1": [1, 8],
            "PHYSHLTH": [88, 30],
            "MENTHLTH": [2, 77],
            "SLEPTIM1": [7, 77],
            "_AGEG5YR": [1, 14],
            "_BMI5": [2500, 9999],
            "_SMOKER3": [1, 9],
            "_DRNKWK2": [1400, 99900],
            "PA3MIN_": [150, 118602],
            "_MICHD": [1, 2],
            "CHCCOPD3": [1, 7],
            "CVDSTRK3": [2, 9],
            "ADDEPEV3": [1, 2],
            "DIABETE4": [1, 4],
            "_LLCPWT": [123.4, 0.5],
        }
    )
    decoded = decode_brfss_person(raw, year=2023)

    assert decoded["year"].tolist() == [2023, 2023]
    assert decoded["state_fips"].tolist() == ["01", "12"]

    assert decoded["sex"].tolist() == ["male", "female"]
    assert decoded["race_ethnicity"].tolist() == ["white_non_hispanic", "hispanic"]

    assert bool(decoded.loc[0, "has_healthcare_coverage"]) is True
    assert bool(decoded.loc[1, "has_healthcare_coverage"]) is False

    assert bool(decoded.loc[0, "has_personal_doctor"]) is True
    assert bool(decoded.loc[1, "has_personal_doctor"]) is False

    assert bool(decoded.loc[0, "cost_barrier_to_care"]) is True
    assert bool(decoded.loc[1, "cost_barrier_to_care"]) is False

    assert bool(decoded.loc[0, "last_checkup_within_year"]) is True
    assert bool(decoded.loc[1, "last_checkup_within_year"]) is False

    assert decoded.loc[0, "physical_health_days"] == 0
    assert decoded.loc[1, "physical_health_days"] == 30
    assert decoded.loc[0, "mental_health_days"] == 2
    assert pd.isna(decoded.loc[1, "mental_health_days"])
    assert decoded.loc[0, "sleep_hours_per_night"] == 7
    assert pd.isna(decoded.loc[1, "sleep_hours_per_night"])

    assert decoded.loc[0, "age"] == 21
    assert pd.isna(decoded.loc[1, "age"])

    assert decoded.loc[0, "bmi"] == 25.0
    assert pd.isna(decoded.loc[1, "bmi"])

    assert bool(decoded.loc[0, "smoker"]) is True
    assert pd.isna(decoded.loc[1, "smoker"])

    assert decoded.loc[0, "alcohol_servings_per_week"] == 14
    assert pd.isna(decoded.loc[1, "alcohol_servings_per_week"])

    assert decoded.loc[0, "exercise_minutes_per_week"] == 150
    assert pd.isna(decoded.loc[1, "exercise_minutes_per_week"])

    assert decoded.loc[0, "label_heart_disease"] == 1
    assert decoded.loc[1, "label_heart_disease"] == 0

    assert decoded.loc[0, "label_chronic_lung_disease"] == 1
    assert pd.isna(decoded.loc[1, "label_chronic_lung_disease"])

    assert decoded.loc[0, "label_stroke"] == 0
    assert pd.isna(decoded.loc[1, "label_stroke"])

    assert decoded.loc[0, "label_depression"] == 1
    assert decoded.loc[1, "label_depression"] == 0

    assert decoded.loc[0, "label_diabetes"] == 1
    assert decoded.loc[1, "label_diabetes"] == 0


def test_decode_brfss_person_clamps_outliers() -> None:
    """decode_brfss_person should clamp alcohol and exercise to contract maxes."""
    raw = pd.DataFrame(
        {
            "_STATE": [1],
            "SEXVAR": [1],
            "_IMPRACE": [2],
            "PRIMINS1": [3],
            "PERSDOC3": [2],
            "MEDCOST1": [2],
            "CHECKUP1": [2],
            "PHYSHLTH": [77],
            "MENTHLTH": [99],
            "_AGEG5YR": [2],
            "_BMI5": [3000],
            "_SMOKER3": [4],
            "_DRNKWK2": [10500],  # 105.00 drinks/wk -> clamp to 70
            "PA3MIN_": [5000],  # clamp to 2000
            "_MICHD": [2],
            "CHCCOPD3": [2],
            "CVDSTRK3": [2],
            "ADDEPEV3": [2],
            "DIABETE4": [3],
            "_LLCPWT": [1.0],
        }
    )
    decoded = decode_brfss_person(raw, year=2023)
    assert decoded.loc[0, "alcohol_servings_per_week"] == 70
    assert decoded.loc[0, "exercise_minutes_per_week"] == 2000
    assert pd.isna(decoded.loc[0, "physical_health_days"])
    assert pd.isna(decoded.loc[0, "mental_health_days"])
    assert pd.isna(decoded.loc[0, "sleep_hours_per_night"])


def test_decode_brfss_person_rounds_exercise_minutes() -> None:
    """decode_brfss_person should round near-zero float noise before Int64 casting."""
    raw = pd.DataFrame(
        {
            "_STATE": [1],
            "SEXVAR": [2],
            "_IMPRACE": [6],
            "PRIMINS1": [88],
            "PERSDOC3": [7],
            "MEDCOST1": [7],
            "CHECKUP1": [7],
            "PHYSHLTH": [1],
            "MENTHLTH": [88],
            "_AGEG5YR": [2],
            "_BMI5": [3000],
            "_SMOKER3": [4],
            "_DRNKWK2": [0],
            "PA3MIN_": [5.397605346934028e-79],
            "_MICHD": [2],
            "CHCCOPD3": [2],
            "CVDSTRK3": [2],
            "ADDEPEV3": [2],
            "DIABETE4": [3],
            "_LLCPWT": [1.0],
        }
    )
    decoded = decode_brfss_person(raw, year=2023)
    assert decoded.loc[0, "exercise_minutes_per_week"] == 0
    assert pd.isna(decoded.loc[0, "has_personal_doctor"])
    assert pd.isna(decoded.loc[0, "cost_barrier_to_care"])
    assert pd.isna(decoded.loc[0, "last_checkup_within_year"])
    assert decoded.loc[0, "physical_health_days"] == 1
    assert decoded.loc[0, "mental_health_days"] == 0


def test_brfss_v2_feature_contract_separates_scenario_and_adjustment_inputs() -> None:
    """The v2 contract should keep user-editable fields separate from covariates."""
    assert BRFSS_SCENARIO_FEATURES == (
        "age",
        "bmi",
        "smoker",
        "alcohol_servings_per_week",
        "exercise_minutes_per_week",
    )
    assert "sex" in BRFSS_ADJUSTMENT_FEATURES
    assert "race_ethnicity" in BRFSS_ADJUSTMENT_FEATURES
    assert "has_healthcare_coverage" in BRFSS_ADJUSTMENT_FEATURES
    assert "physical_health_days" in BRFSS_ADJUSTMENT_FEATURES
    assert "mental_health_days" in BRFSS_ADJUSTMENT_FEATURES
    assert set(BRFSS_SCENARIO_FEATURES).isdisjoint(BRFSS_ADJUSTMENT_FEATURES)
    assert BRFSS_LABEL_FEATURE_EXCLUSIONS["depression"] == ("mental_health_days",)
    assert "physical_health_days" in BRFSS_LABEL_FEATURE_EXCLUSIONS["heart_disease"]
