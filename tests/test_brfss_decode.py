"""Unit tests for BRFSS decode logic (no network, no large files)."""

import pandas as pd  # type: ignore[import-untyped]

from longevity_lab.pipeline.build_brfss_tables import decode_brfss_person


def test_decode_brfss_person_happy_path() -> None:
    """decode_brfss_person should map v1 features/labels and missing codes."""
    raw = pd.DataFrame(
        {
            "_STATE": [1, 12],
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


def test_decode_brfss_person_rounds_exercise_minutes() -> None:
    """decode_brfss_person should round near-zero float noise before Int64 casting."""
    raw = pd.DataFrame(
        {
            "_STATE": [1],
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
