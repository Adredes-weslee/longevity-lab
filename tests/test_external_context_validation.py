"""Tests for external reasonableness checks against CDC PLACES context."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd  # type: ignore[import-untyped]
import pytest

from longevity_lab.pipeline.build_places_tables import places_county_year_parquet
from longevity_lab.pipeline.validate_external_context import (
    EXTERNAL_VALIDATION_CAVEAT,
    build_external_validation_report,
    places_external_validation_report_csv_path,
    places_external_validation_report_json_path,
    provenance_external_validation_path,
    validate_external_context,
)


def _places_context_frame() -> pd.DataFrame:
    """Return a tiny wide PLACES context table for validation tests."""
    return pd.DataFrame(
        [
            {
                "release_year": 2025,
                "year": 2023,
                "state_fips": "06",
                "state_abbr": "CA",
                "state_name": "California",
                "county_fips": "06001",
                "county_name": "Alameda",
                "geography_name": "Alameda County, California",
                "places_total_population": 1000,
                "places_total_pop_18plus": 100,
                "places_coronary_heart_disease_estimate_year": 2023,
                "places_diabetes_estimate_year": 2023,
                "places_coronary_heart_disease_crude_prevalence": 5.0,
                "places_diabetes_crude_prevalence": 10.0,
            },
            {
                "release_year": 2025,
                "year": 2023,
                "state_fips": "06",
                "state_abbr": "CA",
                "state_name": "California",
                "county_fips": "06013",
                "county_name": "Contra Costa",
                "geography_name": "Contra Costa County, California",
                "places_total_population": 3000,
                "places_total_pop_18plus": 300,
                "places_coronary_heart_disease_estimate_year": 2023,
                "places_diabetes_estimate_year": 2023,
                "places_coronary_heart_disease_crude_prevalence": 9.0,
                "places_diabetes_crude_prevalence": 14.0,
            },
        ]
    )


def _model_aggregate_frame() -> pd.DataFrame:
    """Return model aggregate risk patterns keyed by state and condition."""
    return pd.DataFrame(
        [
            {
                "condition_id": "heart_disease",
                "state_fips": "06",
                "mean_predicted_probability": 0.07,
                "n_model_rows": 25,
            },
            {
                "condition_id": "diabetes",
                "state_fips": "06",
                "mean_predicted_probability": 0.11,
                "n_model_rows": 25,
            },
        ]
    )


def test_external_validation_report_compares_model_aggregates_to_places() -> None:
    """Validation should compare aggregate model probabilities with PLACES estimates."""
    report = build_external_validation_report(
        model_aggregates=_model_aggregate_frame(),
        places_context=_places_context_frame(),
    )

    assert set(report["condition_id"]) == {"heart_disease", "diabetes"}
    assert set(report["geography_level"]) == {"state"}
    assert report["places_is_model_based_context"].tolist() == [True, True]
    assert set(report["places_reference_kind"]) == {"population_weighted_crude_prevalence"}

    heart = report.loc[report["condition_id"] == "heart_disease"].iloc[0]
    assert heart["places_measure_id"] == "CHD"
    assert heart["places_crude_prevalence"] == pytest.approx(8.0)
    assert heart["places_crude_prevalence_probability"] == pytest.approx(0.08)
    assert heart["absolute_difference"] == pytest.approx(-0.01)
    assert "not independent person-level labels" in EXTERNAL_VALIDATION_CAVEAT


def test_validate_external_context_writes_report_outputs_and_provenance(tmp_path: Path) -> None:
    """The validation CLI path should write JSON/CSV report outputs plus provenance."""
    base_dir = tmp_path / "data"
    places_path = places_county_year_parquet(base_dir)
    places_path.parent.mkdir(parents=True, exist_ok=True)
    _places_context_frame().to_parquet(places_path, index=False)

    model_path = tmp_path / "model_aggregates.csv"
    model_path.parent.mkdir(parents=True, exist_ok=True)
    _model_aggregate_frame().to_csv(model_path, index=False)

    validate_external_context(
        base_dir=base_dir,
        places_year=2025,
        model_aggregate_path=model_path,
        bundle_dir=None,
        force=False,
        dry_run=False,
    )

    json_path = places_external_validation_report_json_path(base_dir, places_year=2025)
    csv_path = places_external_validation_report_csv_path(base_dir, places_year=2025)
    provenance_path = provenance_external_validation_path(base_dir, places_year=2025)
    assert json_path.exists()
    assert csv_path.exists()
    assert provenance_path.exists()

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["caveat"] == EXTERNAL_VALIDATION_CAVEAT
    assert payload["places_release_year"] == 2025
    assert len(payload["rows"]) == 2

    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    assert provenance["dataset_name"] == "places_external_context_validation"
    assert provenance["report_outputs"] == [
        csv_path.relative_to(base_dir).as_posix(),
        json_path.relative_to(base_dir).as_posix(),
    ]
    assert provenance["model_input"] == model_path.as_posix()
    assert "source_registry_by_year" in provenance
    assert "not independent person-level labels" in provenance["places_context_caveat"]


def test_bundle_prediction_aggregates_use_survey_weights() -> None:
    """Raw bundle predictions should aggregate with persisted BRFSS survey weights."""
    model_rows = pd.DataFrame(
        [
            {
                "condition_id": "heart_disease",
                "state_fips": "06",
                "predicted_probability": 0.0,
                "survey_weight": 99.0,
            },
            {
                "condition_id": "heart_disease",
                "state_fips": "06",
                "predicted_probability": 1.0,
                "survey_weight": 1.0,
            },
        ]
    )

    report = build_external_validation_report(
        model_aggregates=model_rows,
        places_context=_places_context_frame(),
    )

    heart = report.loc[report["condition_id"] == "heart_disease"].iloc[0]
    assert heart["model_mean_predicted_probability"] == pytest.approx(0.01)
