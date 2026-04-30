"""Tests for causal workbench report generation."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd  # type: ignore[import-untyped]

from longevity_lab.causal.datasets import load_smoking_lung_config
from longevity_lab.causal.reports import run_smoking_lung_workbench


def _write_report_input(path: Path, *, rows: int = 120) -> None:
    """Write deterministic integrated rows with overlap for the smoking workbench."""
    records: list[dict[str, object]] = []
    for idx in range(rows):
        smoker = idx % 4 in {0, 1}
        older = idx % 6 in {0, 1, 2}
        high_aqi = idx % 5 == 0
        outcome = smoker or (older and high_aqi) or idx % 17 == 0
        records.append(
            {
                "year": 2023,
                "state_fips": ["01", "06", "12"][idx % 3],
                "sex": "female" if idx % 2 == 0 else "male",
                "race_ethnicity": [
                    "white_non_hispanic",
                    "black_non_hispanic",
                    "hispanic",
                    "other_non_hispanic",
                ][idx % 4],
                "age": 30 + (idx % 50),
                "bmi": 21.0 + float(idx % 16),
                "smoker": smoker,
                "alcohol_servings_per_week": idx % 14,
                "exercise_minutes_per_week": 30 + (idx % 10) * 30,
                "annual_aqi": 45 + (idx % 9) * 8,
                "has_healthcare_coverage": idx % 11 != 0,
                "has_personal_doctor": idx % 7 != 0,
                "cost_barrier_to_care": idx % 13 == 0,
                "last_checkup_within_year": idx % 5 != 0,
                "sleep_hours_per_night": 5 + (idx % 4),
                "physical_health_days": idx % 30,
                "mental_health_days": (idx * 2) % 30,
                "label_chronic_lung_disease": int(outcome),
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
    assert payload["serving_policy"]["api_exposed"] is False
    assert payload["serving_policy"]["ui_exposed"] is False
    assert payload["analysis_dataset"]["rows"] == 120
    assert payload["estimate"]["method"] == "weighted_logistic_g_computation"
    assert -1.0 <= payload["estimate"]["risk_difference"] <= 1.0
    assert payload["diagnostics"]["propensity_overlap"]["treated_rows"] > 0
    assert payload["diagnostics"]["propensity_overlap"]["control_rows"] > 0
    assert payload["diagnostics"]["diagnostic_gate"]["status"] in {"passed", "warning"}
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
    assert payload["negative_controls"]["exposures"] == [
        {
            "name": "within_stratum_permuted_smoking_status",
            "status": "ok",
            "reason": "Implemented as `permuted_treatment_placebo` with a fixed seed.",
        }
    ]
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
    assert "## Negative Controls" in markdown
    assert "sex_at_birth_if_available" in markdown
    assert "## Sensitivity Checks" in markdown
    assert "dowhy_placebo_subset_random_common_cause_refutations" in markdown
