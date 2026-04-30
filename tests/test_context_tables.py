"""Tests for ACS/SVI context feature table processing."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pandas as pd  # type: ignore[import-untyped]
import pytest

import longevity_lab.pipeline.download_acs as download_acs_module
from longevity_lab.pipeline.build_context_tables import (
    CONTEXT_FEATURE_COLUMNS,
    SCENARIO_EDITABLE_COLUMNS,
    build_context_tables,
    build_county_context_table,
    build_state_context_table,
    load_context_feature_config,
)
from longevity_lab.pipeline.download_acs import (
    ACS_QUERY_VARIABLES,
    acs_api_url,
    acs_api_urls,
    acs_raw_json_path,
    download_acs,
    merge_acs_json_chunks,
)
from longevity_lab.pipeline.download_svi import svi_county_csv_path, svi_county_csv_url

ACS_COLUMNS = [
    "NAME",
    "B01003_001E",
    "B01003_001M",
    "B17001_001E",
    "B17001_001M",
    "B17001_002E",
    "B17001_002M",
    "B19013_001E",
    "B19013_001M",
    "B15003_001E",
    "B15003_001M",
    "B15003_022E",
    "B15003_022M",
    "B15003_023E",
    "B15003_023M",
    "B15003_024E",
    "B15003_024M",
    "B15003_025E",
    "B15003_025M",
    "B27010_001E",
    "B27010_001M",
    "B27010_017E",
    "B27010_017M",
    "B27010_033E",
    "B27010_033M",
    "B27010_050E",
    "B27010_050M",
    "B27010_066E",
    "B27010_066M",
    "B18101_001E",
    "B18101_001M",
    "B18101_004E",
    "B18101_004M",
    "B18101_007E",
    "B18101_007M",
    "B18101_010E",
    "B18101_010M",
    "B18101_013E",
    "B18101_013M",
    "B18101_016E",
    "B18101_016M",
    "B18101_019E",
    "B18101_019M",
    "B18101_023E",
    "B18101_023M",
    "B18101_026E",
    "B18101_026M",
    "B18101_029E",
    "B18101_029M",
    "B18101_032E",
    "B18101_032M",
    "B18101_035E",
    "B18101_035M",
    "B18101_038E",
    "B18101_038M",
    "B28002_001E",
    "B28002_001M",
    "B28002_004E",
    "B28002_004M",
]


def _acs_row(
    *,
    name: str,
    state: str,
    county: str | None = None,
    population: int = 1_000,
    poverty_total: int = 1_000,
    poverty_below: int = 100,
    median_income: int = 70_000,
    education_total: int = 800,
    bachelor_counts: tuple[int, int, int, int] = (100, 50, 30, 20),
    insurance_total: int = 1_000,
    uninsured_counts: tuple[int, int, int, int] = (10, 20, 30, 40),
    disability_total: int = 1_000,
    disability_each: int = 10,
    internet_total: int = 1_000,
    broadband: int = 700,
) -> dict[str, str]:
    """Build one ACS API-like row with estimates and MOE values."""
    row = {column: "1" for column in ACS_COLUMNS}
    row.update(
        {
            "NAME": name,
            "B01003_001E": str(population),
            "B17001_001E": str(poverty_total),
            "B17001_002E": str(poverty_below),
            "B19013_001E": str(median_income),
            "B15003_001E": str(education_total),
            "B15003_022E": str(bachelor_counts[0]),
            "B15003_023E": str(bachelor_counts[1]),
            "B15003_024E": str(bachelor_counts[2]),
            "B15003_025E": str(bachelor_counts[3]),
            "B27010_001E": str(insurance_total),
            "B27010_017E": str(uninsured_counts[0]),
            "B27010_033E": str(uninsured_counts[1]),
            "B27010_050E": str(uninsured_counts[2]),
            "B27010_066E": str(uninsured_counts[3]),
            "B18101_001E": str(disability_total),
            "B28002_001E": str(internet_total),
            "B28002_004E": str(broadband),
            "state": state,
        }
    )
    for column in [
        "B18101_004E",
        "B18101_007E",
        "B18101_010E",
        "B18101_013E",
        "B18101_016E",
        "B18101_019E",
        "B18101_023E",
        "B18101_026E",
        "B18101_029E",
        "B18101_032E",
        "B18101_035E",
        "B18101_038E",
    ]:
        row[column] = str(disability_each)
    if county is not None:
        row["county"] = county
    return row


def _write_acs_json(path: Path, rows: list[dict[str, str]], *, county: bool) -> None:
    headers = [*ACS_COLUMNS, "state"]
    if county:
        headers.append("county")
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [headers, *[[row[column] for column in headers] for row in rows]]
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_svi_csv(path: Path) -> None:
    frame = pd.DataFrame(
        [
            {
                "ST": "06",
                "STATE": "California",
                "STCNTY": "06001",
                "COUNTY": "Alameda",
                "RPL_THEMES": 0.2,
                "RPL_THEME1": 0.3,
                "RPL_THEME2": 0.4,
                "RPL_THEME3": 0.5,
                "RPL_THEME4": 0.6,
            },
            {
                "ST": "06",
                "STATE": "California",
                "STCNTY": "06013",
                "COUNTY": "Contra Costa",
                "RPL_THEMES": 0.6,
                "RPL_THEME1": 0.7,
                "RPL_THEME2": 0.8,
                "RPL_THEME3": 0.9,
                "RPL_THEME4": -999,
            },
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)


def _write_context_raw_inputs(base_dir: Path, *, year: int) -> None:
    _write_acs_json(
        acs_raw_json_path(base_dir, year=year, geography="county"),
        [
            _acs_row(name="Alameda County, California", state="06", county="001"),
            _acs_row(
                name="Contra Costa County, California",
                state="06",
                county="013",
                population=3_000,
                poverty_below=300,
            ),
        ],
        county=True,
    )
    _write_acs_json(
        acs_raw_json_path(base_dir, year=year, geography="state"),
        [
            _acs_row(
                name="California",
                state="06",
                population=4_000,
                poverty_total=4_000,
                poverty_below=500,
                median_income=80_000,
            )
        ],
        county=False,
    )
    _write_svi_csv(svi_county_csv_path(base_dir, year=year))


def test_context_config_keeps_curated_context_out_of_scenario_inputs() -> None:
    """Context config should declare curated ACS/SVI fields, not editable scenario inputs."""
    config = load_context_feature_config()

    assert config.schema_version == 1
    assert "acs_poverty_percent" in CONTEXT_FEATURE_COLUMNS
    assert "acs_broadband_percent" in CONTEXT_FEATURE_COLUMNS
    assert "svi_overall_percentile" in CONTEXT_FEATURE_COLUMNS
    assert "svi_theme4_housing_transportation_percentile" in CONTEXT_FEATURE_COLUMNS
    assert set(CONTEXT_FEATURE_COLUMNS).isdisjoint(SCENARIO_EDITABLE_COLUMNS)


def test_download_urls_are_scriptable_without_network() -> None:
    """Download modules should expose deterministic source URLs for raw inputs."""
    acs_url = acs_api_url(year=2022, geography="county", api_key="test-key")
    parsed = urlparse(acs_url)
    query = parse_qs(parsed.query)

    assert parsed.netloc == "api.census.gov"
    assert query["for"] == ["county:*"]
    assert query["in"] == ["state:*"]
    assert query["key"] == ["test-key"]
    assert "B17001_002E" in query["get"][0]

    acs_urls = acs_api_urls(year=2022, geography="county", api_key="test-key")
    requested_variables = set()
    for url in acs_urls:
        parsed_chunk = urlparse(url)
        query_chunk = parse_qs(parsed_chunk.query)
        variables = query_chunk["get"][0].split(",")
        assert len(variables) <= 50
        assert variables[0] == "NAME"
        assert query_chunk["for"] == ["county:*"]
        assert query_chunk["in"] == ["state:*"]
        requested_variables.update(variables)
    assert set(ACS_QUERY_VARIABLES).issubset(requested_variables)

    assert svi_county_csv_url(2022) == (
        "https://svi.cdc.gov/Documents/Data/2022/csv/states_counties/SVI_2022_US_county.csv"
    )


def test_download_acs_rejects_unsupported_year_before_download(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ACS downloader should reject unsupported registry years before network I/O."""
    called = False

    def fake_download_file(*_args: object, **_kwargs: object) -> None:
        nonlocal called
        called = True

    monkeypatch.setattr(download_acs_module, "download_file", fake_download_file)

    with pytest.raises(NotImplementedError, match="does not support year 2025"):
        download_acs(
            base_dir=tmp_path / "data",
            years=[2025],
            geography="state",
            api_key=None,
            force=False,
            dry_run=False,
        )

    assert called is False


def test_merge_acs_json_chunks_preserves_all_chunk_variables(tmp_path: Path) -> None:
    """Chunked ACS API responses should merge into the raw JSON shape the builder reads."""
    first = tmp_path / "part1.json"
    second = tmp_path / "part2.json"
    out = tmp_path / "merged.json"
    first.write_text(
        json.dumps(
            [
                ["NAME", "B01003_001E", "state", "county"],
                ["Alameda County, California", "1000", "06", "001"],
            ]
        ),
        encoding="utf-8",
    )
    second.write_text(
        json.dumps(
            [
                ["NAME", "B28002_004M", "state", "county"],
                ["Alameda County, California", "12", "06", "001"],
            ]
        ),
        encoding="utf-8",
    )

    merge_acs_json_chunks([first, second], out, geography="county")

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload == [
        ["NAME", "state", "county", "B01003_001E", "B28002_004M"],
        ["Alameda County, California", "06", "001", "1000", "12"],
    ]


def test_build_county_context_table_derives_acs_and_svi_features(tmp_path: Path) -> None:
    """County context should derive curated ACS rates and attach SVI county fields."""
    base_dir = tmp_path / "data"
    year = 2022
    _write_context_raw_inputs(base_dir, year=year)

    county = build_county_context_table(
        acs_json_path=acs_raw_json_path(base_dir, year=year, geography="county"),
        svi_csv_path=svi_county_csv_path(base_dir, year=year),
        year=year,
    )

    assert county["county_fips"].tolist() == ["06001", "06013"]
    first = county.iloc[0]
    assert first["year"] == year
    assert first["state_fips"] == "06"
    assert first["geography_name"] == "Alameda County, California"
    assert first["acs_total_population"] == 1_000
    assert first["acs_poverty_percent"] == pytest.approx(10.0)
    assert first["acs_median_household_income"] == 70_000
    assert first["acs_bachelors_degree_or_higher_percent"] == pytest.approx(25.0)
    assert first["acs_uninsured_percent"] == pytest.approx(10.0)
    assert first["acs_disability_percent"] == pytest.approx(12.0)
    assert first["acs_broadband_percent"] == pytest.approx(70.0)
    assert first["acs_poverty_percent_moe_available"] is True
    assert first["svi_overall_percentile"] == pytest.approx(0.2)

    second = county.iloc[1]
    assert pd.isna(second["svi_theme4_housing_transportation_percentile"])


def test_build_state_context_table_uses_state_acs_and_weighted_county_svi(
    tmp_path: Path,
) -> None:
    """State context should use state ACS rows and population-weighted county SVI values."""
    base_dir = tmp_path / "data"
    year = 2022
    _write_context_raw_inputs(base_dir, year=year)
    county = build_county_context_table(
        acs_json_path=acs_raw_json_path(base_dir, year=year, geography="county"),
        svi_csv_path=svi_county_csv_path(base_dir, year=year),
        year=year,
    )

    state = build_state_context_table(
        acs_json_path=acs_raw_json_path(base_dir, year=year, geography="state"),
        county_context=county,
        year=year,
    )

    assert state["state_fips"].tolist() == ["06"]
    assert "county_fips" not in state.columns
    first = state.iloc[0]
    assert first["geography_name"] == "California"
    assert first["acs_poverty_percent"] == pytest.approx(12.5)
    assert first["acs_median_household_income"] == 80_000
    assert first["svi_overall_percentile"] == pytest.approx(0.5)


def test_build_context_tables_cli_is_idempotent(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The CLI build path should skip existing complete outputs unless forced."""
    base_dir = tmp_path / "data"
    year = 2022
    _write_context_raw_inputs(base_dir, year=year)

    build_context_tables(base_dir=base_dir, years=[year], force=False, dry_run=False)
    build_context_tables(base_dir=base_dir, years=[year], force=False, dry_run=False)

    county_path = base_dir / "processed" / "context" / "context_county_year.parquet"
    state_path = base_dir / "processed" / "context" / "context_state_year.parquet"
    assert county_path.exists()
    assert state_path.exists()
    assert set(pd.read_parquet(county_path)["year"].tolist()) == {year}
    assert set(pd.read_parquet(state_path)["year"].tolist()) == {year}
    assert "Skip build (exists)" in capsys.readouterr().out

    provenance_path = base_dir / "processed" / "provenance" / f"context_tables_{year}.json"
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    assert provenance["sources"]
    assert any("api.census.gov" in source for source in provenance["sources"])
    assert any("SVI_2022_US_county.csv" in source for source in provenance["sources"])
    assert provenance["context_feature_schema_version"] == 1
    assert str(year) in provenance["source_registry_by_year"]
