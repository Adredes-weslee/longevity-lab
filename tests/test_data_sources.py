"""Tests for the public data-source registry."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from longevity_lab.pipeline.provenance import registry_provenance_extra
from longevity_lab.pipeline.sources import DataSourceRegistry, load_data_source_registry


def test_data_source_registry_loads_default_sources() -> None:
    """The default registry should expose the initial CDC and EPA sources."""
    registry = load_data_source_registry()
    indexed = registry.by_id()

    assert registry.schema_version == 1
    assert set(indexed) == {
        "cdc_brfss_llcp_xpt",
        "cdc_brfss_llcp_codebook",
        "epa_airdata_annual_aqi_by_county",
        "epa_airdata_annual_conc_by_monitor",
        "census_acs5_api_context",
        "cdc_atsdr_svi_us_county_csv",
    }


def test_data_source_registry_formats_year_templates() -> None:
    """Registry templates should produce concrete URLs and paths for supported years."""
    registry = load_data_source_registry()

    brfss = registry.require("cdc_brfss_llcp_xpt")
    codebook = registry.require("cdc_brfss_llcp_codebook")
    epa = registry.require("epa_airdata_annual_aqi_by_county")
    epa_concentration = registry.require("epa_airdata_annual_conc_by_monitor")
    acs = registry.require("census_acs5_api_context")
    svi = registry.require("cdc_atsdr_svi_us_county_csv")

    assert brfss.download_url(year=2023).endswith("/2023/files/LLCP2023XPT.zip")
    assert codebook.download_url(year=2023).endswith("/2023/zip/codebook23_llcp-v2-508.zip")
    assert epa.download_url(year=2023).endswith("/annual_aqi_by_county_2023.zip")
    assert epa_concentration.download_url(year=2023).endswith("/annual_conc_by_monitor_2023.zip")
    assert acs.download_url(year=2024).endswith("/data/2024/acs/acs5")
    assert svi.download_url(year=2022).endswith("/SVI_2022_US_county.csv")
    assert brfss.landing_path(year=2023) == "external/brfss/2023/"


def test_data_source_registry_rejects_unsupported_year() -> None:
    """Explicit year support should prevent accidental unsupported BRFSS downloads."""
    registry = load_data_source_registry()
    source = registry.require("cdc_brfss_llcp_xpt")

    with pytest.raises(NotImplementedError, match="does not support year 2022"):
        source.download_url(year=2022)


def test_data_source_registry_rejects_duplicate_source_ids(tmp_path: Path) -> None:
    """Duplicate source IDs should fail rather than silently shadowing records."""
    payload = {
        "schema_version": 1,
        "sources": [
            {
                "source_id": "duplicate",
                "title": "A",
                "official_url": "https://example.com/{year}",
                "download_url_template": "https://example.com/{year}.zip",
                "year_support": {"mode": "explicit", "years": [2023]},
                "geography": "test",
                "expected_file_pattern": "file.csv",
                "checksum_policy": "test",
                "license_note": "test",
                "local_landing_path": "external/test/{year}/",
            },
            {
                "source_id": "duplicate",
                "title": "B",
                "official_url": "https://example.org/{year}",
                "download_url_template": "https://example.org/{year}.zip",
                "year_support": {"mode": "explicit", "years": [2023]},
                "geography": "test",
                "expected_file_pattern": "file.csv",
                "checksum_policy": "test",
                "license_note": "test",
                "local_landing_path": "external/test/{year}/",
            },
        ],
    }
    registry_path = tmp_path / "sources.yaml"
    registry_path.write_text(json.dumps(payload), encoding="utf-8")
    registry = load_data_source_registry(registry_path)

    with pytest.raises(ValueError, match="Duplicate source_id"):
        registry.by_id()


def test_registry_provenance_extra_contains_source_metadata() -> None:
    """Provenance extras should include source, checksum, license, and landing-path fields."""
    registry = load_data_source_registry()

    extra = registry_provenance_extra(
        registry=registry,
        source_ids=["epa_airdata_annual_aqi_by_county"],
        year=2023,
    )

    source_record = extra["source_registry"]["sources"][0]
    assert source_record["source_id"] == "epa_airdata_annual_aqi_by_county"
    assert source_record["download_url"].endswith("annual_aqi_by_county_2023.zip")
    assert source_record["checksum_policy"]
    assert source_record["license_note"]
    assert source_record["local_landing_path"] == (
        "external/epa_airdata/annual_aqi_by_county_2023/"
    )


def test_registry_provenance_extra_contains_epa_concentration_metadata() -> None:
    """EPA annual concentration downloads should have registry-backed provenance."""
    registry = load_data_source_registry()

    extra = registry_provenance_extra(
        registry=registry,
        source_ids=[
            "epa_airdata_annual_aqi_by_county",
            "epa_airdata_annual_conc_by_monitor",
        ],
        year=2023,
    )

    indexed = {source["source_id"]: source for source in extra["source_registry"]["sources"]}
    concentration = indexed["epa_airdata_annual_conc_by_monitor"]
    assert concentration["download_url"].endswith("annual_conc_by_monitor_2023.zip")
    assert concentration["expected_file_pattern"] == "annual_conc_by_monitor_2023.csv"


def test_data_source_registry_model_rejects_unknown_fields() -> None:
    """The registry contract should be strict so misspelled metadata fails tests."""
    payload = {
        "schema_version": 1,
        "sources": [],
        "unexpected": True,
    }

    with pytest.raises(ValueError):
        DataSourceRegistry.model_validate(payload)
