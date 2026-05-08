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
    (artifacts_dir / "evidence" / "public-evidence-test").mkdir(parents=True)
    (artifacts_dir / "evidence" / "public-evidence-test" / "manifest.json").write_text(
        json.dumps({"bundle_id": "public-evidence-test"}),
        encoding="utf-8",
    )
    evidence_processed = artifacts_dir / "evidence" / "public-evidence-test" / "processed"
    (evidence_processed / "context").mkdir(parents=True)
    (evidence_processed / "context" / "context_state_year.parquet").write_bytes(b"parquet")
    (evidence_processed / "context" / "context_county_year.parquet").write_bytes(b"parquet")
    (evidence_processed / "places").mkdir(parents=True)
    (evidence_processed / "places" / "places_county_year.parquet").write_bytes(b"parquet")
    (evidence_processed / "validation").mkdir(parents=True)
    (evidence_processed / "validation" / "places_external_context_validation_2025.json").write_text(
        "{}",
        encoding="utf-8",
    )
    (evidence_processed / "reports" / "causal").mkdir(parents=True)
    (evidence_processed / "reports" / "causal" / "manifest_report.json").write_text(
        "{}",
        encoding="utf-8",
    )

    monkeypatch.setenv("LONGEVITY_LAB_DATA_DIR", str(data_dir))
    monkeypatch.setenv("LONGEVITY_LAB_ARTIFACTS_DIR", str(artifacts_dir))
    monkeypatch.setenv("LONGEVITY_LAB_EVIDENCE_BUNDLE", "public-evidence-test")
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
    artifacts = {item["asset_id"]: item for item in groups["model_artifacts"]["assets"]}
    assert artifacts["public_evidence_bundle"]["exists"] is True
    assert artifacts["public_evidence_bundle"]["path"] == "evidence/public-evidence-test"
    public_evidence = {
        item["asset_id"]: item for item in groups["public_evidence_bundle"]["assets"]
    }
    assert groups["public_evidence_bundle"]["ready_count"] == 5
    assert public_evidence["bundle_county_context"]["exists"] is True
    assert public_evidence["bundle_county_context"]["path"] == (
        "evidence/public-evidence-test/processed/context/context_county_year.parquet"
    )
    assert public_evidence["bundle_causal_reports"]["exists"] is True
    all_paths = [asset["path"] for group in payload["asset_groups"] for asset in group["assets"]]
    assert all(not Path(path).is_absolute() for path in all_paths)

    feature_inventory = payload["feature_inventory"]
    assert "pm25_mean" in feature_inventory["scenario_editable"]
    assert "ozone_mean" in feature_inventory["scenario_editable"]
    assert "acs_poverty_percent" in feature_inventory["available_pipeline_context_features"]

    gaps = {item["gap_id"]: item for item in payload["inactive_gaps"]}
    assert "context_not_active" in gaps
    assert "places_validation_only" in gaps


def test_evidence_status_does_not_mark_unconfigured_evidence_bundle_ready(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A generic artifacts/evidence directory is not a configured public bundle."""
    data_dir = tmp_path / "data"
    artifacts_dir = tmp_path / "artifacts"
    (artifacts_dir / "evidence").mkdir(parents=True)

    monkeypatch.setenv("LONGEVITY_LAB_DATA_DIR", str(data_dir))
    monkeypatch.setenv("LONGEVITY_LAB_ARTIFACTS_DIR", str(artifacts_dir))
    monkeypatch.delenv("LONGEVITY_LAB_EVIDENCE_BUNDLE", raising=False)
    monkeypatch.delenv("LONGEVITY_LAB_ENGINE", raising=False)
    monkeypatch.delenv("LONGEVITY_LAB_ARTIFACT_BUNDLE", raising=False)

    get_settings.cache_clear()
    try:
        with TestClient(create_app()) as client:
            response = client.get("/api/evidence/status")
    finally:
        get_settings.cache_clear()

    assert response.status_code == 200
    groups = {item["group_id"]: item for item in response.json()["asset_groups"]}
    artifacts = {item["asset_id"]: item for item in groups["model_artifacts"]["assets"]}
    assert artifacts["public_evidence_bundle"]["exists"] is False
    assert artifacts["public_evidence_bundle"]["path"] == "evidence/__unconfigured__"


def test_evidence_status_rejects_unsafe_evidence_bundle_id(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Evidence status should not resolve bundle IDs outside artifacts/evidence."""
    data_dir = tmp_path / "data"
    artifacts_dir = tmp_path / "artifacts"
    (artifacts_dir / "outside").mkdir(parents=True)

    monkeypatch.setenv("LONGEVITY_LAB_DATA_DIR", str(data_dir))
    monkeypatch.setenv("LONGEVITY_LAB_ARTIFACTS_DIR", str(artifacts_dir))
    monkeypatch.setenv("LONGEVITY_LAB_EVIDENCE_BUNDLE", "../outside")
    monkeypatch.delenv("LONGEVITY_LAB_ENGINE", raising=False)
    monkeypatch.delenv("LONGEVITY_LAB_ARTIFACT_BUNDLE", raising=False)

    get_settings.cache_clear()
    try:
        with TestClient(create_app()) as client:
            response = client.get("/api/evidence/status")
    finally:
        get_settings.cache_clear()

    assert response.status_code == 200
    groups = {item["group_id"]: item for item in response.json()["asset_groups"]}
    artifacts = {item["asset_id"]: item for item in groups["model_artifacts"]["assets"]}
    assert artifacts["public_evidence_bundle"]["exists"] is False
    assert artifacts["public_evidence_bundle"]["path"] == "evidence/__invalid__"
