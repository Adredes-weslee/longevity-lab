"""Tests for EPA AirData processing logic."""

from pathlib import Path

import pandas as pd  # type: ignore[import-untyped]

from longevity_lab.pipeline.build_epa_tables import build_state_year_table, state_name_to_fips


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
