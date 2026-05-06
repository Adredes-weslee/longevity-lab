"""Tests for causal subgroup and heterogeneous-effect reporting."""

from __future__ import annotations

from pathlib import Path

import pandas as pd  # type: ignore[import-untyped]
import pytest

from longevity_lab.causal.datasets import load_smoking_lung_config, prepare_causal_dataset
from longevity_lab.causal.heterogeneity import (
    build_heterogeneity_not_run,
    run_heterogeneity_analysis,
)


def test_heterogeneity_reports_subgroups_and_optional_dependency_skips(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reportable strata should estimate effects while optional methods skip cleanly."""
    monkeypatch.setattr(
        "longevity_lab.causal.heterogeneity._has_optional_dependency",
        lambda import_name: False,
    )
    input_path = tmp_path / "integrated_person_year.parquet"
    _write_balanced_heterogeneity_input(input_path)
    config = load_smoking_lung_config()
    prepared = prepare_causal_dataset(input_path=input_path, config=config)

    payload = run_heterogeneity_analysis(prepared, config)

    assert payload["status"] == "estimated"
    assert payload["policy"] == {
        "method": "within_subgroup_weighted_logistic_g_computation",
        "min_cell_size_per_treatment_arm": 25,
        "min_total_rows": 50,
        "min_rows_inside_configured_overlap": 50,
        "required_overlap_bounds": [0.05, 0.95],
        "effect_scale": "risk_difference",
    }
    estimated = [item for item in payload["subgroups"] if item["status"] == "ok"]
    assert estimated
    assert {item["stratum"] for item in estimated} >= {"sex", "race_ethnicity", "state_fips"}
    assert all(item["estimate"] is not None for item in estimated)
    assert all(
        item["diagnostics"]["diagnostic_gate"]["status"] in {"passed", "warning"}
        for item in estimated
    )
    optional_by_name = {item["name"]: item for item in payload["optional_methods"]}
    assert optional_by_name["causal_forest_dml"]["status"] == "skipped"
    assert optional_by_name["causal_forest_dml"]["dependency"] == "econml"
    assert "not installed" in optional_by_name["causal_forest_dml"]["reason"]
    assert optional_by_name["dowhy_heterogeneity_refuters"]["status"] == "skipped"


def test_heterogeneity_suppresses_effects_when_min_cell_size_fails(tmp_path: Path) -> None:
    """Subgroup estimates should not be present when conservative cell checks fail."""
    input_path = tmp_path / "integrated_person_year.parquet"
    _write_balanced_heterogeneity_input(input_path)
    config = load_smoking_lung_config()
    prepared = prepare_causal_dataset(input_path=input_path, config=config)

    payload = run_heterogeneity_analysis(
        prepared,
        config,
        min_cell_size=500,
        min_total_rows=1_000,
        min_overlap_rows=1_000,
    )

    assert payload["status"] == "no_reportable_subgroups"
    assert payload["subgroups"]
    assert all(item["status"] == "skipped" for item in payload["subgroups"])
    assert all(item["estimate"] is None for item in payload["subgroups"])
    assert any("minimum cell size" in item["reason"] for item in payload["subgroups"])


def test_heterogeneity_not_run_payload_is_explicit() -> None:
    """Failed primary diagnostics should still yield a typed heterogeneity record."""
    payload = build_heterogeneity_not_run("primary overlap failed")

    assert payload["status"] == "failed_diagnostic"
    assert payload["subgroups"] == []
    assert payload["candidate_strata"] == []
    assert payload["warnings"] == ["primary overlap failed"]
    assert {item["name"] for item in payload["optional_methods"]} == {
        "causal_forest_dml",
        "dowhy_heterogeneity_refuters",
    }


def _write_balanced_heterogeneity_input(path: Path) -> None:
    records: list[dict[str, object]] = []
    row_index = 0
    for state_fips in ("01", "06"):
        for sex in ("female", "male"):
            for race_ethnicity in ("white_non_hispanic", "black_non_hispanic"):
                for smoker in (False, True):
                    for repeat in range(30):
                        age = 25 + ((repeat + row_index) % 50)
                        outcome = (
                            (smoker and repeat % 5 != 0)
                            or (not smoker and repeat % 7 == 0)
                            or age >= 65
                        )
                        records.append(
                            {
                                "year": 2023,
                                "state_fips": state_fips,
                                "sex": sex,
                                "race_ethnicity": race_ethnicity,
                                "age": age,
                                "bmi": 22.0 + float((repeat + row_index) % 14),
                                "smoker": smoker,
                                "alcohol_servings_per_week": (repeat + row_index) % 16,
                                "exercise_minutes_per_week": 60 + (repeat % 8) * 30,
                                "annual_aqi": 45 if state_fips == "01" else 82,
                                "has_healthcare_coverage": repeat % 11 != 0,
                                "has_personal_doctor": repeat % 7 != 0,
                                "cost_barrier_to_care": repeat % 13 == 0,
                                "last_checkup_within_year": repeat % 5 != 0,
                                "label_chronic_lung_disease": int(outcome),
                                "survey_weight": 1.0 + float(repeat % 4) * 0.25,
                            }
                        )
                        row_index += 1
    pd.DataFrame.from_records(records).to_parquet(path, index=False)
