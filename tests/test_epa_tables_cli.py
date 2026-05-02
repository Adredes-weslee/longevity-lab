"""Tests for EPA AirData CLI behavior."""

from __future__ import annotations

from pathlib import Path

import pandas as pd  # type: ignore[import-untyped]
import pytest

from longevity_lab.pipeline import download_epa_airdata
from longevity_lab.pipeline.build_epa_tables import main as build_epa_tables_main
from longevity_lab.pipeline.ingest import build_ingest_paths


def _epa_airdata_annual_conc_csv(base_dir: Path, year: int) -> Path:
    return (
        base_dir
        / "external"
        / "epa_airdata"
        / f"annual_conc_by_monitor_{year}"
        / f"annual_conc_by_monitor_{year}.csv"
    )


def _epa_county_year_parquet(base_dir: Path) -> Path:
    return base_dir / "processed" / "epa_airdata" / "epa_county_year.parquet"


def _write_minimal_epa_csv(path: Path, *, year: int) -> None:
    frame = pd.DataFrame(
        [
            {
                "State": "California",
                "County": "A",
                "Year": year,
                "Days with AQI": 365,
                "Median AQI": 50,
            }
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)


def _write_minimal_epa_annual_conc_csv(path: Path, *, year: int) -> None:
    frame = pd.DataFrame(
        [
            {
                "State Code": "06",
                "County Code": "001",
                "Site Num": "0001",
                "Parameter Code": 88101,
                "POC": 1,
                "Parameter Name": "PM2.5 - Local Conditions",
                "Pollutant Standard": "PM25 Annual 2012",
                "Metric Used": "Observed Values",
                "Year": year,
                "Observation Count": 365,
                "Observation Percent": 95.0,
                "Completeness Indicator": "Y",
                "Arithmetic Mean": 8.5,
                "State Name": "California",
                "County Name": "A",
            },
            {
                "State Code": "06",
                "County Code": "001",
                "Site Num": "0002",
                "Parameter Code": 44201,
                "POC": 1,
                "Parameter Name": "Ozone",
                "Pollutant Standard": "Ozone 8-hour 2015",
                "Metric Used": "Daily maximum 8-hour average",
                "Year": year,
                "Observation Count": 300,
                "Observation Percent": 90.0,
                "Completeness Indicator": "Y",
                "Arithmetic Mean": 0.04,
                "State Name": "California",
                "County Name": "A",
            },
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)


def test_build_epa_tables_does_not_skip_when_missing_years(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """If output exists but does not contain the requested years, rebuild."""
    base_dir = tmp_path / "data"
    paths = build_ingest_paths(base_dir)

    for year in [2022, 2023]:
        _write_minimal_epa_csv(paths.epa_airdata_annual_aqi_csv(year), year=year)
        _write_minimal_epa_annual_conc_csv(
            _epa_airdata_annual_conc_csv(base_dir, year),
            year=year,
        )

    output_path = paths.epa_state_year_parquet()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([{"year": 2022, "state_fips": "06", "annual_aqi": 50}]).to_parquet(
        output_path,
        index=False,
    )

    build_epa_tables_main(["--base-dir", str(base_dir), "--years", "2022,2023"])

    out = pd.read_parquet(output_path)
    assert set(out["year"].tolist()) == {2022, 2023}
    assert {"pm25_mean", "ozone_mean"}.issubset(set(out.columns))

    county_out = pd.read_parquet(_epa_county_year_parquet(base_dir))
    assert set(county_out["year"].tolist()) == {2022, 2023}
    assert {"annual_aqi", "pm25_mean", "ozone_mean"}.issubset(set(county_out.columns))

    captured = capsys.readouterr().out
    assert "Skip build" not in captured


def test_download_epa_airdata_fetches_aqi_and_annual_concentration_without_network(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Downloader should plan AQI and pollutant annual-summary downloads without network."""
    base_dir = tmp_path / "data"
    calls: list[tuple[str, str]] = []

    def fake_download_file(
        url: str,
        dest_path: Path,
        *,
        force: bool,
        dry_run: bool,
    ) -> None:
        calls.append((url, dest_path.name))
        if not dry_run:
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            dest_path.write_bytes(b"zip")

    def fake_extract_zip(zip_path: Path, dest_dir: Path, *, dry_run: bool) -> list[Path]:
        if dry_run:
            return []
        dest_dir.mkdir(parents=True, exist_ok=True)
        csv_path = dest_dir / zip_path.name.replace(".zip", ".csv")
        csv_path.write_text("", encoding="utf-8")
        return [csv_path]

    monkeypatch.setattr(download_epa_airdata, "download_file", fake_download_file)
    monkeypatch.setattr(download_epa_airdata, "extract_zip", fake_extract_zip)

    download_epa_airdata.main(["--base-dir", str(base_dir), "--year", "2023"])

    assert calls == [
        (
            "https://aqs.epa.gov/aqsweb/airdata/annual_aqi_by_county_2023.zip",
            "annual_aqi_by_county_2023.zip",
        ),
        (
            "https://aqs.epa.gov/aqsweb/airdata/annual_conc_by_monitor_2023.zip",
            "annual_conc_by_monitor_2023.zip",
        ),
    ]


def test_download_epa_airdata_normalizes_nested_annual_concentration_csv(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Downloader should expose nested EPA annual-concentration CSVs at the expected path."""
    base_dir = tmp_path / "data"

    def fake_download_file(
        url: str,
        dest_path: Path,
        *,
        force: bool,
        dry_run: bool,
    ) -> None:
        if not dry_run:
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            dest_path.write_bytes(b"zip")

    def fake_extract_zip(zip_path: Path, dest_dir: Path, *, dry_run: bool) -> list[Path]:
        if dry_run:
            return []
        dest_dir.mkdir(parents=True, exist_ok=True)
        if zip_path.name.startswith("annual_conc"):
            csv_path = dest_dir / "annual_conc_by_monitor_2023" / "annual_conc_by_monitor_2023.csv"
        else:
            csv_path = dest_dir / "annual_aqi_by_county_2023.csv"
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        csv_path.write_text("header\n", encoding="utf-8")
        return [csv_path]

    monkeypatch.setattr(download_epa_airdata, "download_file", fake_download_file)
    monkeypatch.setattr(download_epa_airdata, "extract_zip", fake_extract_zip)

    stale_root_csv = _epa_airdata_annual_conc_csv(base_dir, 2023)
    stale_root_csv.parent.mkdir(parents=True, exist_ok=True)
    stale_root_csv.write_text("stale\n", encoding="utf-8")

    download_epa_airdata.main(["--base-dir", str(base_dir), "--year", "2023"])

    assert stale_root_csv.exists()
    assert stale_root_csv.read_text(encoding="utf-8") == "header\n"


def test_download_epa_airdata_does_not_promote_stale_nested_csv(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Normalization should only promote files extracted in the current run."""
    base_dir = tmp_path / "data"

    def fake_download_file(
        url: str,
        dest_path: Path,
        *,
        force: bool,
        dry_run: bool,
    ) -> None:
        if not dry_run:
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            dest_path.write_bytes(b"zip")

    def fake_extract_zip(zip_path: Path, dest_dir: Path, *, dry_run: bool) -> list[Path]:
        if dry_run:
            return []
        dest_dir.mkdir(parents=True, exist_ok=True)
        csv_path = dest_dir / "annual_aqi_by_county_2023.csv"
        if zip_path.name.startswith("annual_conc"):
            csv_path = dest_dir / "unrelated_current_extract.csv"
        csv_path.write_text("current\n", encoding="utf-8")
        return [csv_path]

    stale_nested_csv = (
        base_dir
        / "external"
        / "epa_airdata"
        / "annual_conc_by_monitor_2023"
        / "annual_conc_by_monitor_2023"
        / "annual_conc_by_monitor_2023.csv"
    )
    stale_nested_csv.parent.mkdir(parents=True, exist_ok=True)
    stale_nested_csv.write_text("stale\n", encoding="utf-8")

    monkeypatch.setattr(download_epa_airdata, "download_file", fake_download_file)
    monkeypatch.setattr(download_epa_airdata, "extract_zip", fake_extract_zip)

    download_epa_airdata.main(["--base-dir", str(base_dir), "--year", "2023"])

    assert not _epa_airdata_annual_conc_csv(base_dir, 2023).exists()
