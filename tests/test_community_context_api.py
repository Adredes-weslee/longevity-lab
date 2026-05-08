"""Tests for community context and research-report API surfaces."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pandas as pd  # type: ignore[import-untyped]
import pytest
from fastapi.testclient import TestClient

from longevity_lab.api.main import create_app
from longevity_lab.config import get_settings


@pytest.fixture
def community_client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[TestClient]:
    """Yield an API client with isolated community-context fixtures."""
    data_dir = tmp_path / "data"
    artifacts_dir = tmp_path / "artifacts"
    _write_context_fixtures(data_dir)
    _write_places_fixtures(data_dir)
    _write_causal_report(data_dir)

    monkeypatch.setenv("LONGEVITY_LAB_DATA_DIR", str(data_dir))
    monkeypatch.setenv("LONGEVITY_LAB_ARTIFACTS_DIR", str(artifacts_dir))
    monkeypatch.delenv("LONGEVITY_LAB_ENGINE", raising=False)
    monkeypatch.delenv("LONGEVITY_LAB_ARTIFACT_BUNDLE", raising=False)

    get_settings.cache_clear()
    try:
        with TestClient(create_app()) as test_client:
            yield test_client
    finally:
        get_settings.cache_clear()


def test_community_overview_surfaces_context_places_and_causal_reports(
    community_client: TestClient,
) -> None:
    """The overview should expose context/research evidence without absolute local paths."""
    response = community_client.get(
        "/api/community/overview?year=2023&places_year=2025&state_fips=06&county_fips=06001"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["contract_version"] == "v2"
    assert "does not directly change Explorer personal risk scores" in payload["caveat"]

    state = payload["state_context"]
    assert state["available"] is True
    assert state["label"] == "California"
    assert state["source_path"] == "processed/context/context_state_year.parquet"
    assert any(item["feature"] == "acs_poverty_percent" for item in state["features"])
    assert state["options"][0]["selected"] is True

    county = payload["county_context"]
    assert county["available"] is True
    assert county["county_fips"] == "06001"
    assert "not injected into person-level scoring" in county["caveat"]

    places = payload["places_context"]
    assert places["available"] is True
    assert places["county_fips"] == "06001"
    assert any(
        item["feature"] == "places_diabetes_crude_prevalence" and item["formatted_value"] == "10.0%"
        for item in places["features"]
    )

    validation = payload["places_validation"]
    assert validation["available"] is True
    assert validation["row_count"] == 2
    assert validation["rows"][0]["condition_id"] == "diabetes"
    assert validation["rows"][0]["absolute_difference"] == pytest.approx(0.02)
    malformed_row = next(row for row in validation["rows"] if row["condition_id"] == "malformed")
    assert malformed_row["geography_level"] == "state"
    assert malformed_row["model_mean_predicted_probability"] is None
    assert validation["report_path"] == (
        "processed/validation/places_external_context_validation_2025.json"
    )

    reports = payload["causal_reports"]
    assert len(reports) == 1
    assert reports[0]["question_id"] == "bmi_diabetes"
    assert reports[0]["risk_difference"] == pytest.approx(0.07)
    assert reports[0]["diagnostic_status"] == "passed"
    assert "separate from predictive Explorer scenario deltas" in reports[0]["caveat"]

    all_paths = [
        state["source_path"],
        county["source_path"],
        places["source_path"],
        validation["report_path"],
        reports[0]["report_path"],
        reports[0]["markdown_path"],
    ]
    assert all(path is not None and not Path(path).is_absolute() for path in all_paths)


def test_community_overview_handles_missing_local_assets(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Missing community assets should return safe unavailable summaries."""
    data_dir = tmp_path / "data"
    artifacts_dir = tmp_path / "artifacts"
    monkeypatch.setenv("LONGEVITY_LAB_DATA_DIR", str(data_dir))
    monkeypatch.setenv("LONGEVITY_LAB_ARTIFACTS_DIR", str(artifacts_dir))
    monkeypatch.delenv("LONGEVITY_LAB_ENGINE", raising=False)
    monkeypatch.delenv("LONGEVITY_LAB_ARTIFACT_BUNDLE", raising=False)

    get_settings.cache_clear()
    try:
        with TestClient(create_app()) as test_client:
            response = test_client.get("/api/community/overview")
    finally:
        get_settings.cache_clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["state_context"]["available"] is False
    assert payload["county_context"]["available"] is False
    assert payload["places_context"]["available"] is False
    assert payload["places_validation"]["available"] is False
    assert payload["causal_reports"] == []
    assert payload["state_context"]["source_path"] == "processed/context/context_state_year.parquet"


def test_community_overview_falls_back_when_requested_geography_is_absent(
    community_client: TestClient,
) -> None:
    """Unknown state/county requests should fall back to available local context rows."""
    response = community_client.get(
        "/api/community/overview?year=2023&places_year=2025&state_fips=99&county_fips=99999"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["state_context"]["state_fips"] == "06"
    assert payload["county_context"]["county_fips"] == "06001"


def _write_context_fixtures(data_dir: Path) -> None:
    context_dir = data_dir / "processed" / "context"
    context_dir.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "year": 2023,
                "state_fips": "06",
                "geography_name": "California",
                "acs_poverty_percent": 12.5,
                "acs_total_population": 39000000,
                "svi_overall_percentile": 0.42,
            }
        ]
    ).to_parquet(context_dir / "context_state_year.parquet", index=False)
    pd.DataFrame(
        [
            {
                "year": 2023,
                "state_fips": "06",
                "county_fips": "06001",
                "geography_name": "Alameda County, California",
                "acs_poverty_percent": 10.1,
                "acs_total_population": 1600000,
                "svi_overall_percentile": 0.25,
            },
            {
                "year": 2023,
                "state_fips": "06",
                "county_fips": "06013",
                "geography_name": "Contra Costa County, California",
                "acs_poverty_percent": 8.8,
                "acs_total_population": 1100000,
                "svi_overall_percentile": 0.2,
            },
        ]
    ).to_parquet(context_dir / "context_county_year.parquet", index=False)


def _write_places_fixtures(data_dir: Path) -> None:
    places_dir = data_dir / "processed" / "places"
    validation_dir = data_dir / "processed" / "validation"
    places_dir.mkdir(parents=True)
    validation_dir.mkdir(parents=True)
    pd.DataFrame(
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
                "places_total_pop_18plus": 800,
                "places_estimate_year_min": 2023,
                "places_estimate_year_max": 2023,
                "places_diabetes_estimate_year": 2023,
                "places_diabetes_crude_prevalence": 10.0,
                "places_diabetes_crude_prevalence_low": 9.0,
                "places_diabetes_crude_prevalence_high": 11.0,
            }
        ]
    ).to_parquet(places_dir / "places_county_year.parquet", index=False)
    (validation_dir / "places_external_context_validation_2025.json").write_text(
        json.dumps(
            {
                "places_release_year": 2025,
                "caveat": "PLACES context caveat.",
                "summary": {"conditions_compared": ["diabetes"], "rows": 1},
                "rows": [
                    {
                        "condition_id": "diabetes",
                        "geography_level": "county",
                        "release_year": 2025,
                        "state_fips": "06",
                        "county_fips": "06001",
                        "geography_name": "Alameda County, California",
                        "model_mean_predicted_probability": 0.12,
                        "places_crude_prevalence_probability": 0.1,
                        "absolute_difference": 0.02,
                        "comparison_direction": "model_higher",
                        "places_reference_kind": "county_crude_prevalence",
                    },
                    {
                        "condition_id": "malformed",
                        "geography_level": "tract",
                        "state_fips": "06",
                        "geography_name": "Malformed validation row",
                        "model_mean_predicted_probability": [0.12],
                        "places_crude_prevalence_probability": {"value": 0.1},
                        "absolute_difference": ["bad"],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )


def _write_causal_report(data_dir: Path) -> None:
    causal_dir = data_dir / "processed" / "reports" / "causal" / "bmi_diabetes"
    causal_dir.mkdir(parents=True)
    report_path = causal_dir / "bmi_diabetes_report.json"
    report_path.write_text(
        json.dumps(
            {
                "question_id": "bmi_diabetes",
                "title": "BMI and diagnosed diabetes",
                "status": "exploratory_assumption_bound",
                "analysis_dataset": {"rows": 180},
                "question": {
                    "treatment": {"column": "bmi_obesity_range"},
                    "outcome": {"column": "label_diabetes"},
                    "estimand": "risk_difference",
                },
                "estimate": {
                    "method": "weighted_logistic_g_computation",
                    "risk_difference": 0.07,
                },
                "diagnostics": {"diagnostic_gate": {"status": "passed"}},
                "heterogeneity": {"status": "estimated"},
            }
        ),
        encoding="utf-8",
    )
    report_path.with_suffix(".md").write_text("# BMI and diagnosed diabetes\n", encoding="utf-8")
