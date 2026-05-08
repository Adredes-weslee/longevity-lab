"""Tests for causal workbench report generation."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd  # type: ignore[import-untyped]
import pytest

from longevity_lab.causal.datasets import (
    load_causal_config_for_question,
    load_causal_workbench_config,
    load_smoking_lung_config,
)
from longevity_lab.causal.reports import run_causal_workbench, run_smoking_lung_workbench


def _write_report_input(path: Path, *, rows: int = 120) -> None:
    """Write deterministic integrated rows with overlap for the smoking workbench."""
    records: list[dict[str, object]] = []
    for idx in range(rows):
        smoker = idx % 4 in {0, 1}
        older = idx % 6 in {0, 1, 2}
        high_aqi = idx % 5 == 0
        outcome = smoker or (older and high_aqi) or idx % 17 == 0
        sex = "female" if idx % 2 == 0 else "male"
        alcohol = idx % 18
        heavy_alcohol = alcohol > (7 if sex == "female" else 14)
        bmi = 21.0 + float(idx % 16)
        exercise = 30 + (idx % 10) * 30
        records.append(
            {
                "year": 2023,
                "state_fips": ["01", "06", "12"][idx % 3],
                "sex": sex,
                "race_ethnicity": [
                    "white_non_hispanic",
                    "black_non_hispanic",
                    "hispanic",
                    "other_non_hispanic",
                ][idx % 4],
                "age": 30 + (idx % 50),
                "bmi": bmi,
                "smoker": smoker,
                "alcohol_servings_per_week": alcohol,
                "exercise_minutes_per_week": exercise,
                "annual_aqi": 45 + (idx % 9) * 8,
                "has_healthcare_coverage": idx % 11 != 0,
                "has_personal_doctor": idx % 7 != 0,
                "cost_barrier_to_care": idx % 13 == 0,
                "last_checkup_within_year": idx % 5 != 0,
                "sleep_hours_per_night": 5 + (idx % 4),
                "physical_health_days": idx % 30,
                "mental_health_days": (idx * 2) % 30,
                "label_chronic_lung_disease": int(outcome),
                "label_diabetes": int((bmi >= 30.0) or older or idx % 23 == 0),
                "label_depression": int(heavy_alcohol or exercise < 120 or idx % 19 == 0),
                "survey_weight": 1.0 + float(idx % 5) * 0.5,
            }
        )
    pd.DataFrame.from_records(records).to_parquet(path, index=False)


def test_run_smoking_lung_workbench_writes_json_and_markdown(tmp_path: Path) -> None:
    """The workbench should produce assumption-bound reports outside serving paths."""
    input_path = tmp_path / "integrated_person_year.parquet"
    output_dir = tmp_path / "reports"
    _write_report_input(input_path)

    result = run_smoking_lung_workbench(
        config=load_smoking_lung_config(),
        input_path=input_path,
        output_dir=output_dir,
    )

    assert result.json_path == output_dir / "smoking_lung_report.json"
    assert result.markdown_path == output_dir / "smoking_lung_report.md"
    assert result.json_path.exists()
    assert result.markdown_path.exists()

    payload = json.loads(result.json_path.read_text(encoding="utf-8"))
    assert payload["question_id"] == "smoking_chronic_lung_disease"
    assert Path(payload["run_config_path"]).parts[-3:] == (
        "conf",
        "causal",
        "smoking_lung.yaml",
    )
    assert payload["serving_policy"]["api_exposed"] is False
    assert payload["serving_policy"]["ui_exposed"] is False
    assert payload["question"]["treatment"]["derivation"] == {
        "kind": "direct_binary",
        "source_column": "smoker",
    }
    assert payload["analysis_dataset"]["rows"] == 120
    assert payload["estimate"]["method"] == "weighted_logistic_g_computation"
    assert -1.0 <= payload["estimate"]["risk_difference"] <= 1.0
    assert payload["diagnostics"]["propensity_overlap"]["treated_rows"] > 0
    assert payload["diagnostics"]["propensity_overlap"]["control_rows"] > 0
    assert payload["diagnostics"]["diagnostic_gate"]["status"] in {"passed", "warning"}
    assert payload["heterogeneity"]["status"] in {"estimated", "no_reportable_subgroups"}
    assert payload["heterogeneity"]["policy"]["method"] == (
        "within_subgroup_weighted_logistic_g_computation"
    )
    assert any(item["name"] == "sex" for item in payload["heterogeneity"]["candidate_strata"])
    optional_methods = {item["name"]: item for item in payload["heterogeneity"]["optional_methods"]}
    assert "causal_forest_dml" in optional_methods
    assert optional_methods["causal_forest_dml"]["status"] in {"skipped", "ok"}
    assert {item["name"] for item in payload["refutations"]} >= {
        "permuted_treatment_placebo",
        "subset_refit",
        "random_common_cause",
    }
    assert {item["name"] for item in payload["negative_controls"]["outcomes"]} == {
        "sex_at_birth_if_available",
        "race_ethnicity_if_available",
        "adult_height_if_available",
        "interview_month_if_available",
    }
    assert payload["negative_controls"]["exposures"][0]["name"] == (
        "within_stratum_permuted_smoking_status"
    )
    assert payload["negative_controls"]["exposures"][0]["status"] == "not_run"
    assert (
        "within-stratum placebo exposure" in payload["negative_controls"]["exposures"][0]["reason"]
    )
    sensitivity_by_name = {item["name"]: item for item in payload["sensitivity_checks"]}
    assert sensitivity_by_name["dowhy_placebo_subset_random_common_cause_refutations"] == {
        "name": "dowhy_placebo_subset_random_common_cause_refutations",
        "status": "ok",
        "reason": (
            "Implemented in PR12 through permuted-treatment placebo, subset-refit, "
            "and random-common-cause refutation prototypes."
        ),
    }
    assert all("status" in item for item in payload["sensitivity_checks"])

    markdown = result.markdown_path.read_text(encoding="utf-8")
    assert "# Current smoking and diagnosed chronic lung disease" in markdown
    assert "Not served through the FastAPI API or React UI" in markdown
    assert "weighted_logistic_g_computation" in markdown
    assert "## Heterogeneity" in markdown
    assert "causal_forest_dml" in markdown
    assert "## Negative Controls" in markdown
    assert "sex_at_birth_if_available" in markdown
    assert "## Sensitivity Checks" in markdown
    assert "dowhy_placebo_subset_random_common_cause_refutations" in markdown


@pytest.mark.parametrize(
    ("question", "expected_question_id"),
    [
        ("activity_diabetes", "physical_activity_diabetes"),
        ("bmi_diabetes", "bmi_diabetes"),
        ("alcohol_depression", "alcohol_depression"),
    ],
)
def test_run_causal_workbench_writes_reports_for_each_pr22_question(
    tmp_path: Path,
    question: str,
    expected_question_id: str,
) -> None:
    """Each PR22 question should produce a non-serving audit report."""
    input_path = tmp_path / "integrated_person_year.parquet"
    output_dir = tmp_path / question
    _write_report_input(input_path, rows=180)
    config = load_causal_config_for_question(question)

    result = run_causal_workbench(config=config, input_path=input_path, output_dir=output_dir)

    payload = json.loads(result.json_path.read_text(encoding="utf-8"))
    assert payload["question_id"] == expected_question_id
    assert "derivation" in payload["question"]["treatment"]
    assert Path(payload["run_config_path"]).parts[-3:] == ("conf", "causal", f"{question}.yaml")
    assert payload["serving_policy"] == {
        "api_exposed": False,
        "ui_exposed": False,
        "statement": "Not served through the FastAPI API or React UI.",
    }
    assert payload["analysis_dataset"]["rows"] > 0
    assert payload["status"] in {"exploratory_assumption_bound", "failed_diagnostic"}
    assert "heterogeneity" in payload
    assert "optional_methods" in payload["heterogeneity"]
    if payload["status"] == "exploratory_assumption_bound":
        assert payload["estimate"]["method"] == "weighted_logistic_g_computation"
        assert "risk_difference" in payload["estimate"]
    else:
        assert payload["estimate"] is None
    assert payload["diagnostics"]["diagnostic_gate"]["status"] in {
        "passed",
        "warning",
        "failed",
    }
    assert all("status" in item for item in payload["negative_controls"]["exposures"])
    for item in payload["negative_controls"]["exposures"]:
        if item["name"].startswith("within_stratum_permuted_"):
            expected_status = (
                "failed_diagnostic" if payload["status"] == "failed_diagnostic" else "not_run"
            )
            assert item["status"] == expected_status
    assert all("status" in item for item in payload["sensitivity_checks"])
    markdown = result.markdown_path.read_text(encoding="utf-8")
    assert "Not served through the FastAPI API or React UI" in markdown
    assert "## Estimate" in markdown
    assert "## Limitations" in markdown


def test_run_causal_workbench_handles_nullable_boolean_adjustment_columns(
    tmp_path: Path,
) -> None:
    """Full processed Parquet can expose adjustment flags as nullable boolean columns."""
    input_path = tmp_path / "integrated_person_year.parquet"
    output_dir = tmp_path / "nullable-bool"
    _write_report_input(input_path, rows=180)
    frame = pd.read_parquet(input_path)
    for column in (
        "has_healthcare_coverage",
        "has_personal_doctor",
        "cost_barrier_to_care",
        "last_checkup_within_year",
    ):
        frame[column] = frame[column].astype("boolean")
    frame.loc[0, "has_healthcare_coverage"] = pd.NA
    frame.to_parquet(input_path, index=False)
    config = load_causal_config_for_question("bmi_diabetes")

    result = run_causal_workbench(config=config, input_path=input_path, output_dir=output_dir)

    payload = json.loads(result.json_path.read_text(encoding="utf-8"))
    assert payload["question_id"] == "bmi_diabetes"
    assert payload["status"] in {"exploratory_assumption_bound", "failed_diagnostic"}


def test_run_causal_workbench_writes_diagnostic_failure_report(tmp_path: Path) -> None:
    """A question with unmet prerequisites should still produce an explicit failure report."""
    input_path = tmp_path / "one_class.parquet"
    output_dir = tmp_path / "failed"
    _write_report_input(input_path, rows=60)
    frame = pd.read_parquet(input_path)
    frame["exercise_minutes_per_week"] = 240
    frame.to_parquet(input_path, index=False)
    config = load_causal_config_for_question("activity_diabetes")

    result = run_causal_workbench(config=config, input_path=input_path, output_dir=output_dir)

    payload = json.loads(result.json_path.read_text(encoding="utf-8"))
    assert payload["status"] == "failed_diagnostic"
    assert payload["estimate"] is None
    assert payload["heterogeneity"]["status"] == "failed_diagnostic"
    assert payload["heterogeneity"]["subgroups"] == []
    assert payload["diagnostics"]["diagnostic_gate"]["status"] == "failed"
    assert all(item["status"] == "failed_diagnostic" for item in payload["sensitivity_checks"])


def test_run_causal_workbench_reports_custom_config_path(tmp_path: Path) -> None:
    """Report provenance should identify the concrete config that was loaded."""
    input_path = tmp_path / "integrated_person_year.parquet"
    output_dir = tmp_path / "custom-output"
    custom_config_path = tmp_path / "custom_activity.yaml"
    _write_report_input(input_path, rows=90)
    custom_config_path.write_text(
        Path("conf/causal/activity_diabetes.yaml")
        .read_text(encoding="utf-8")
        .replace(
            "physical_activity_diabetes_report.json",
            "custom_activity_report.json",
        ),
        encoding="utf-8",
    )
    config = load_causal_workbench_config(custom_config_path)

    result = run_causal_workbench(config=config, input_path=input_path, output_dir=output_dir)

    payload = json.loads(result.json_path.read_text(encoding="utf-8"))
    assert Path(payload["run_config_path"]) == custom_config_path
