"""Tests for EPA AirData processing logic."""

from pathlib import Path

import pandas as pd  # type: ignore[import-untyped]

from longevity_lab.pipeline.build_epa_tables import (
    build_county_year_table,
    build_state_year_table,
    state_name_to_fips,
)


def test_state_name_to_fips() -> None:
    """state_name_to_fips should map supported names and return None otherwise."""
    assert state_name_to_fips("California") == "06"
    assert state_name_to_fips("District Of Columbia") == "11"
    assert state_name_to_fips("Puerto Rico") == "72"
    assert state_name_to_fips("") is None
    assert state_name_to_fips(None) is None
    assert state_name_to_fips(float("nan")) is None
    assert state_name_to_fips("Country Of Mexico") is None


def test_build_state_year_table_weighted_mean_and_drop(tmp_path: Path) -> None:
    """The build step should drop unmapped states and compute weighted mean of Median AQI."""
    csv_path = tmp_path / "annual_aqi_by_county_2023.csv"
    frame = pd.DataFrame(
        [
            {
                "State": "California",
                "County": "A",
                "Year": 2023,
                "Days with AQI": 100,
                "Median AQI": 50,
            },
            {
                "State": "California",
                "County": "B",
                "Year": 2023,
                "Days with AQI": 200,
                "Median AQI": 70,
            },
            {
                "State": "Country Of Mexico",
                "County": "X",
                "Year": 2023,
                "Days with AQI": 365,
                "Median AQI": 10,
            },
        ]
    )
    frame.to_csv(csv_path, index=False)

    result = build_state_year_table(csv_path, year=2023)
    assert result.dropped_rows == 1
    out = result.table
    assert len(out) == 1
    row = out.iloc[0].to_dict()
    assert row["year"] == 2023
    assert row["state_fips"] == "06"
    expected = round((50 * 100 + 70 * 200) / 300)
    assert row["annual_aqi"] == expected


def test_build_state_year_table_clamps_aqi(tmp_path: Path) -> None:
    """AQI values should be clamped to [0, 500]."""
    csv_path = tmp_path / "annual_aqi_by_county_2023.csv"
    frame = pd.DataFrame(
        [
            {
                "State": "California",
                "County": "A",
                "Year": 2023,
                "Days with AQI": 365,
                "Median AQI": 600,
            }
        ]
    )
    frame.to_csv(csv_path, index=False)
    result = build_state_year_table(csv_path, year=2023)
    assert int(result.table.loc[0, "annual_aqi"]) == 500


def test_build_county_year_table_adds_quality_gated_pollutants(tmp_path: Path) -> None:
    """County-year output should add pollutant features only for complete monitor rows."""
    aqi_csv_path = tmp_path / "annual_aqi_by_county_2023.csv"
    pd.DataFrame(
        [
            {
                "State": "California",
                "County": "A",
                "Year": 2023,
                "Days with AQI": 365,
                "Median AQI": 50,
            },
            {
                "State": "California",
                "County": "B",
                "Year": 2023,
                "Days with AQI": 200,
                "Median AQI": 90,
            },
        ]
    ).to_csv(aqi_csv_path, index=False)

    annual_conc_csv_path = tmp_path / "annual_conc_by_monitor_2023.csv"
    pd.DataFrame(
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
                "Year": 2023,
                "Observation Count": 365,
                "Observation Percent": 95.0,
                "Completeness Indicator": "Y",
                "Arithmetic Mean": 8.5,
                "State Name": "California",
                "County Name": "A",
            },
            {
                "State Code": "06",
                "County Code": "003",
                "Site Num": "0002",
                "Parameter Code": 88101,
                "POC": 1,
                "Parameter Name": "PM2.5 - Local Conditions",
                "Pollutant Standard": "PM25 Annual 2012",
                "Metric Used": "Observed Values",
                "Year": 2023,
                "Observation Count": 30,
                "Observation Percent": 20.0,
                "Completeness Indicator": "N",
                "Arithmetic Mean": 20.0,
                "State Name": "California",
                "County Name": "B",
            },
            {
                "State Code": "06",
                "County Code": "001",
                "Site Num": "0003",
                "Parameter Code": 44201,
                "POC": 1,
                "Parameter Name": "Ozone",
                "Pollutant Standard": "Ozone 8-hour 2015",
                "Metric Used": "Daily maximum 8-hour average",
                "Year": 2023,
                "Observation Count": 300,
                "Observation Percent": 88.0,
                "Completeness Indicator": "Y",
                "Arithmetic Mean": 0.041,
                "State Name": "California",
                "County Name": "A",
            },
        ]
    ).to_csv(annual_conc_csv_path, index=False)

    result = build_county_year_table(
        aqi_csv_path,
        annual_conc_csv_path,
        year=2023,
    )

    out = result.table.sort_values(["county_name"]).reset_index(drop=True)
    assert out["state_fips"].tolist() == ["06", "06"]
    assert out["county_fips"].tolist() == ["06001", "06003"]
    assert out["annual_aqi"].tolist() == [50, 90]

    complete = out.loc[out["county_name"] == "A"].iloc[0]
    assert complete["pm25_mean"] == 8.5
    assert complete["pm25_monitor_count"] == 1
    assert bool(complete["pm25_observation_complete"]) is True
    assert complete["ozone_mean"] == 0.041
    assert complete["ozone_monitor_count"] == 1
    assert bool(complete["ozone_observation_complete"]) is True

    incomplete = out.loc[out["county_name"] == "B"].iloc[0]
    assert pd.isna(incomplete["pm25_mean"])
    assert incomplete["pm25_monitor_count"] == 0
    assert bool(incomplete["pm25_observation_complete"]) is False


def test_build_state_year_table_adds_pollutants_from_complete_counties(
    tmp_path: Path,
) -> None:
    """State-year pollutant features should be based on quality-gated county rows."""
    aqi_csv_path = tmp_path / "annual_aqi_by_county_2023.csv"
    pd.DataFrame(
        [
            {
                "State": "California",
                "County": "A",
                "Year": 2023,
                "Days with AQI": 100,
                "Median AQI": 50,
            },
            {
                "State": "California",
                "County": "B",
                "Year": 2023,
                "Days with AQI": 200,
                "Median AQI": 80,
            },
        ]
    ).to_csv(aqi_csv_path, index=False)

    annual_conc_csv_path = tmp_path / "annual_conc_by_monitor_2023.csv"
    pd.DataFrame(
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
                "Year": 2023,
                "Observation Count": 365,
                "Observation Percent": 95.0,
                "Completeness Indicator": "Y",
                "Arithmetic Mean": 7.0,
                "State Name": "California",
                "County Name": "A",
            },
            {
                "State Code": "06",
                "County Code": "003",
                "Site Num": "0002",
                "Parameter Code": 88101,
                "POC": 1,
                "Parameter Name": "PM2.5 - Local Conditions",
                "Pollutant Standard": "PM25 Annual 2012",
                "Metric Used": "Observed Values",
                "Year": 2023,
                "Observation Count": 365,
                "Observation Percent": 40.0,
                "Completeness Indicator": "N",
                "Arithmetic Mean": 30.0,
                "State Name": "California",
                "County Name": "B",
            },
            {
                "State Code": "06",
                "County Code": "001",
                "Site Num": "0003",
                "Parameter Code": 44201,
                "POC": 1,
                "Parameter Name": "Ozone",
                "Pollutant Standard": "Ozone 8-hour 2015",
                "Metric Used": "Daily maximum 8-hour average",
                "Year": 2023,
                "Observation Count": 200,
                "Observation Percent": 85.0,
                "Completeness Indicator": "Y",
                "Arithmetic Mean": 0.039,
                "State Name": "California",
                "County Name": "A",
            },
        ]
    ).to_csv(annual_conc_csv_path, index=False)

    result = build_state_year_table(
        aqi_csv_path,
        year=2023,
        annual_conc_csv_path=annual_conc_csv_path,
    )

    row = result.table.iloc[0].to_dict()
    assert row["annual_aqi"] == round((50 * 100 + 80 * 200) / 300)
    assert row["pm25_mean"] == 7.0
    assert row["pm25_monitor_count"] == 1
    assert bool(row["pm25_observation_complete"]) is True
    assert row["ozone_mean"] == 0.039
    assert row["ozone_monitor_count"] == 1
    assert bool(row["ozone_observation_complete"]) is True
