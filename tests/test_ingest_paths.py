"""Unit tests for the canonical ingest path layout builder."""

from pathlib import Path

from longevity_lab.pipeline.ingest import build_ingest_paths, build_paths


def test_build_ingest_paths_roots(tmp_path: Path) -> None:
    """build_ingest_paths should expose stable top-level directories."""
    base_dir = tmp_path / "data"
    paths = build_ingest_paths(base_dir)

    assert paths.base_dir == base_dir
    assert paths.external_dir == base_dir / "external"
    assert paths.processed_dir == base_dir / "processed"
    assert paths.provenance_dir == base_dir / "processed" / "provenance"
    assert paths.duckdb_path == base_dir / "processed" / "longevity_lab.duckdb"
    assert paths.raw_dir == paths.external_dir

    assert build_paths(base_dir) == paths


def test_build_ingest_paths_year_aware_helpers(tmp_path: Path) -> None:
    """Year-aware helper methods should match the expected dataset layout."""
    base_dir = tmp_path / "data"
    paths = build_ingest_paths(base_dir)

    assert paths.brfss_raw_dir(2023) == base_dir / "external" / "brfss" / "2023"
    assert (
        paths.brfss_person_parquet(2023)
        == base_dir / "processed" / "brfss" / "2023" / "brfss_person.parquet"
    )

    assert paths.epa_airdata_raw_dir() == base_dir / "external" / "epa_airdata"
    assert (
        paths.epa_airdata_annual_aqi_zip(2022)
        == base_dir / "external" / "epa_airdata" / "annual_aqi_by_county_2022.zip"
    )
    assert (
        paths.epa_airdata_annual_aqi_extract_dir(2022)
        == base_dir / "external" / "epa_airdata" / "annual_aqi_by_county_2022"
    )
    assert (
        paths.epa_airdata_annual_aqi_csv(2022)
        == base_dir
        / "external"
        / "epa_airdata"
        / "annual_aqi_by_county_2022"
        / "annual_aqi_by_county_2022.csv"
    )
    assert (
        paths.epa_state_year_parquet()
        == base_dir / "processed" / "epa_airdata" / "annual_aqi_state_year.parquet"
    )

    assert (
        paths.integrated_person_year_parquet(2023)
        == base_dir / "processed" / "integrated" / "2023" / "integrated_person_year.parquet"
    )

    assert (
        paths.provenance_brfss_raw(2023)
        == base_dir / "processed" / "provenance" / "brfss_raw_2023.json"
    )
    assert (
        paths.provenance_brfss_person(2023)
        == base_dir / "processed" / "provenance" / "brfss_person_2023.json"
    )
    assert (
        paths.provenance_epa_airdata_annual_aqi_by_county(2022)
        == base_dir / "processed" / "provenance" / "epa_airdata_annual_aqi_by_county_2022.json"
    )
    assert (
        paths.provenance_epa_airdata_state_year([2021, 2022])
        == base_dir
        / "processed"
        / "provenance"
        / "epa_airdata_annual_aqi_state_year_2021_2022.json"
    )
    assert (
        paths.provenance_integrated_person_year(2023)
        == base_dir / "processed" / "provenance" / "integrated_person_year_2023.json"
    )
