"""Tests for the comprehensive evidence-status API."""

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from longevity_lab.api.main import create_app
from longevity_lab.config import get_settings


@pytest.fixture
def evidence_client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[TestClient]:
    """Yield an API client with isolated data and artifact roots."""
    data_dir = tmp_path / "data"
    artifacts_dir = tmp_path / "artifacts"
    year = 2023

    (data_dir / "external" / "brfss" / str(year)).mkdir(parents=True)
    (data_dir / "external" / "brfss" / str(year) / f"LLCP{year}.XPT").write_bytes(b"xpt")
    (data_dir / "external" / "epa_airdata" / f"annual_aqi_by_county_{year}").mkdir(parents=True)
    (
        data_dir
        / "external"
        / "epa_airdata"
        / f"annual_aqi_by_county_{year}"
        / f"annual_aqi_by_county_{year}.csv"
    ).write_text("state,county,aqi\n", encoding="utf-8")
    (data_dir / "processed" / "brfss" / str(year)).mkdir(parents=True)
    (data_dir / "processed" / "brfss" / str(year) / "brfss_person.parquet").write_bytes(b"parquet")
    (data_dir / "processed" / "integrated" / str(year)).mkdir(parents=True)
    (
        data_dir / "processed" / "integrated" / str(year) / "integrated_person_year.parquet"
    ).write_bytes(b"parquet")
    (data_dir / "processed" / "provenance").mkdir(parents=True)
    (data_dir / "processed" / "provenance" / f"integrated_person_year_{year}.json").write_text(
        json.dumps({"dataset_name": "integrated", "dataset_version": "2023"}),
        encoding="utf-8",
    )

    monkeypatch.setenv("LONGEVITY_LAB_DATA_DIR", str(data_dir))
    monkeypatch.setenv("LONGEVITY_LAB_ARTIFACTS_DIR", str(artifacts_dir))
    monkeypatch.delenv("LONGEVITY_LAB_ENGINE", raising=False)
    monkeypatch.delenv("LONGEVITY_LAB_ARTIFACT_BUNDLE", raising=False)
    monkeypatch.delenv("LONGEVITY_LAB_ARTIFACT_URL", raising=False)
    monkeypatch.delenv("LONGEVITY_LAB_ARTIFACT_SHA256", raising=False)

    get_settings.cache_clear()
    try:
        with TestClient(create_app()) as test_client:
            yield test_client
    finally:
        get_settings.cache_clear()


def test_evidence_status_surfaces_sources_assets_and_gaps(
    evidence_client: TestClient,
) -> None:
    """Evidence status should show active sources, runtime assets, and inactive gaps."""
    response = evidence_client.get("/api/evidence/status?year=2023")

    assert response.status_code == 200
    payload = response.json()
    assert payload["contract_version"] == "v2"
    assert payload["runtime"]["engine_mode"] == "demo"

    sources = {item["source_id"]: item for item in payload["sources"]}
    assert sources["cdc_brfss_llcp_xpt"]["active_in_model"] is True
    assert sources["epa_airdata_annual_aqi_by_county"]["active_in_model"] is True
    assert sources["epa_airdata_annual_conc_by_monitor"]["active_in_model"] is True
    assert sources["cdc_places_county_opendata"]["role"] == "external_validation"

    groups = {item["group_id"]: item for item in payload["asset_groups"]}
    assert groups["raw_sources"]["ready_count"] >= 2
    assert groups["processed_tables"]["ready_count"] >= 2
    all_paths = [asset["path"] for group in payload["asset_groups"] for asset in group["assets"]]
    assert all(not Path(path).is_absolute() for path in all_paths)

    feature_inventory = payload["feature_inventory"]
    assert "pm25_mean" in feature_inventory["scenario_editable"]
    assert "ozone_mean" in feature_inventory["scenario_editable"]
    assert "acs_poverty_percent" in feature_inventory["available_pipeline_context_features"]

    gaps = {item["gap_id"]: item for item in payload["inactive_gaps"]}
    assert "context_not_active" in gaps
    assert "places_validation_only" in gaps
