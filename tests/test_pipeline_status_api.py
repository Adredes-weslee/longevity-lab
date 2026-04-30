"""Tests for the pipeline status API route."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from longevity_lab.api.main import create_app
from longevity_lab.config import get_settings


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """Yield a TestClient configured with a temporary data directory."""
    data_dir = tmp_path / "data"

    year = 2023
    (data_dir / "external" / "brfss" / str(year)).mkdir(parents=True, exist_ok=True)
    (data_dir / "external" / "epa_airdata" / f"annual_aqi_by_county_{year}").mkdir(
        parents=True, exist_ok=True
    )
    (data_dir / "processed" / "provenance").mkdir(parents=True, exist_ok=True)

    (data_dir / "external" / "brfss" / str(year) / f"LLCP{year}.XPT").write_bytes(b"xpt")
    (
        data_dir
        / "external"
        / "epa_airdata"
        / f"annual_aqi_by_county_{year}"
        / f"annual_aqi_by_county_{year}.csv"
    ).write_text("State,County,Year\n", encoding="utf-8")

    provenance_path = data_dir / "processed" / "provenance" / f"brfss_person_{year}.json"
    provenance_path.write_text(
        json.dumps(
            {
                "dataset_name": "brfss_person",
                "dataset_version": str(year),
                "retrieved_at": "2026-03-15T00:00:00+00:00",
                "sources": ["https://example.com"],
                "files": [],
                "rows": 1,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    # Simulate multi-year EPA provenance to ensure the endpoint picks the file that
    # covers the requested year.
    epa_multi_year = (
        data_dir
        / "processed"
        / "provenance"
        / "epa_airdata_annual_aqi_state_year_2021_2022_2023.json"
    )
    epa_multi_year.write_text(
        json.dumps(
            {
                "dataset_name": "epa_airdata_annual_aqi_state_year",
                "dataset_version": "2021_2022_2023",
                "retrieved_at": "2026-03-15T00:00:00+00:00",
                "sources": ["https://example.com"],
                "files": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    # Add a malformed provenance file to ensure the endpoint is resilient to local corruption.
    (data_dir / "processed" / "provenance" / f"integrated_person_year_{year}.json").write_text(
        "{",
        encoding="utf-8",
    )

    monkeypatch.setenv("LONGEVITY_LAB_DATA_DIR", str(data_dir))
    get_settings.cache_clear()
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client
    get_settings.cache_clear()


def test_pipeline_status_returns_artifacts_and_provenance(client: TestClient) -> None:
    """The pipeline status endpoint should return expected artifact and provenance fields."""
    response = client.get("/api/pipeline/status?year=2023")
    assert response.status_code == 200
    payload = response.json()
    assert payload["year"] == 2023
    assert payload["artifacts"]
    assert any(
        item["artifact_id"] == "brfss_xpt" and item["exists"] for item in payload["artifacts"]
    )
    assert any(
        item["artifact_id"] == "epa_aqi_csv" and item["exists"] for item in payload["artifacts"]
    )

    assert payload["provenance"]
    brfss = next(item for item in payload["provenance"] if item["dataset_name"] == "brfss_person")
    assert brfss["dataset_version"] == "2023"
    assert brfss["extra"]["rows"] == 1


def test_pipeline_status_paths_are_relative_to_data_dir(client: TestClient, tmp_path: Path) -> None:
    """The pipeline status endpoint should not leak absolute filesystem paths by default."""
    response = client.get("/api/pipeline/status?year=2023")
    assert response.status_code == 200
    payload = response.json()

    brfss_artifact = next(
        item for item in payload["artifacts"] if item["artifact_id"] == "brfss_xpt"
    )
    assert brfss_artifact["path"].startswith("external/")
    assert tmp_path.as_posix() not in brfss_artifact["path"]

    brfss_prov = next(
        item for item in payload["provenance"] if item["dataset_name"] == "brfss_person"
    )
    assert brfss_prov["path"].startswith("processed/provenance/")
    assert tmp_path.as_posix() not in brfss_prov["path"]


def test_pipeline_status_includes_multi_year_epa_state_year_provenance(client: TestClient) -> None:
    """EPA state-year provenance should include multi-year outputs."""
    response = client.get("/api/pipeline/status?year=2023")
    assert response.status_code == 200
    payload = response.json()
    assert any(
        item["dataset_name"] == "epa_airdata_annual_aqi_state_year"
        for item in payload["provenance"]
    )
