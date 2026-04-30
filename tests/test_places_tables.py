"""Tests for CDC PLACES county context table processing."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pandas as pd  # type: ignore[import-untyped]
import pytest

from longevity_lab.pipeline.build_places_tables import (
    PLACES_CONDITION_MEASURES,
    PLACES_CONTEXT_MEASURES,
    SCENARIO_EDITABLE_COLUMNS,
    build_places_county_context_table,
    build_places_tables,
    places_county_year_parquet,
)
from longevity_lab.pipeline.download_places import (
    PLACES_SOURCE_ID,
    places_county_csv_path,
    places_county_csv_url,
)


def _places_raw_rows() -> list[dict[str, str]]:
    """Return a tiny PLACES-like long table covering selected context measures."""
    measures = [
        ("CHD", "Coronary heart disease among adults", "Health Outcomes", 5.0, 4.0, 6.0),
        (
            "COPD",
            "Chronic obstructive pulmonary disease among adults",
            "Health Outcomes",
            7.0,
            6.0,
            8.0,
        ),
        ("STROKE", "Stroke among adults", "Health Outcomes", 3.0, 2.0, 4.0),
        ("DEPRESSION", "Depression among adults", "Health Outcomes", 20.0, 18.0, 22.0),
        ("DIABETES", "Diagnosed diabetes among adults", "Health Outcomes", 10.0, 9.0, 11.0),
        (
            "CSMOKING",
            "Current cigarette smoking among adults",
            "Health Risk Behaviors",
            15.0,
            13.0,
            17.0,
        ),
        ("BINGE", "Binge drinking among adults", "Health Risk Behaviors", 12.0, 10.0, 14.0),
        (
            "LPA",
            "No leisure-time physical activity among adults",
            "Health Risk Behaviors",
            25.0,
            22.0,
            28.0,
        ),
        ("OBESITY", "Obesity among adults", "Health Outcomes", 30.0, 27.0, 33.0),
        ("SLEEP", "Short sleep duration among adults", "Health Risk Behaviors", 34.0, 31.0, 37.0),
    ]
    counties = [
        ("06", "CA", "California", "Alameda", "06001", "1000", "800", 0.0),
        ("06", "CA", "California", "Contra Costa", "06013", "3000", "2400", 4.0),
    ]
    rows: list[dict[str, str]] = []
    for (
        _,
        state_abbr,
        state_name,
        county_name,
        county_fips,
        population,
        adult_pop,
        offset,
    ) in counties:
        for measure_id, measure, category, value, low, high in measures:
            rows.append(
                {
                    "year": "2022" if measure_id == "SLEEP" else "2023",
                    "stateabbr": state_abbr,
                    "statedesc": state_name,
                    "locationname": county_name,
                    "datasource": "BRFSS",
                    "category": category,
                    "measure": measure,
                    "data_value_unit": "%",
                    "data_value_type": "Crude prevalence",
                    "data_value": str(value + offset),
                    "low_confidence_limit": str(low + offset),
                    "high_confidence_limit": str(high + offset),
                    "totalpopulation": population,
                    "totalpop18plus": adult_pop,
                    "locationid": county_fips,
                    "categoryid": "HLTHOUT",
                    "measureid": measure_id,
                    "datavaluetypeid": "CrdPrv",
                    "short_question_text": measure.split(" among ")[0],
                    "geolocation": "POINT (-122.0 37.0)",
                }
            )
    rows.append(
        {
            **rows[0],
            "data_value_type": "Age-adjusted prevalence",
            "data_value": "99.0",
            "datavaluetypeid": "AgeAdjPrv",
        }
    )
    return rows


def _write_places_raw_csv(path: Path) -> None:
    """Write a tiny PLACES raw CSV fixture."""
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(_places_raw_rows()).to_csv(path, index=False)


def test_places_download_url_uses_official_public_cdc_endpoint() -> None:
    """PLACES downloader should use the official public CDC data endpoint without tokens."""
    url = places_county_csv_url(2025)
    parsed = urlparse(url)
    query = parse_qs(parsed.query)

    assert PLACES_SOURCE_ID == "cdc_places_county_opendata"
    assert parsed.netloc == "data.cdc.gov"
    assert parsed.path == "/api/views/swc5-untb/rows.csv"
    assert query == {"accessType": ["DOWNLOAD"]}
    assert "token" not in url.lower()


def test_places_measure_contract_covers_conditions_and_behaviors() -> None:
    """The curated PLACES context should cover modeled conditions plus behavior context."""
    condition_measure_ids = {spec.measure_id for spec in PLACES_CONDITION_MEASURES.values()}
    context_measure_ids = {spec.measure_id for spec in PLACES_CONTEXT_MEASURES}

    assert condition_measure_ids == {"CHD", "COPD", "STROKE", "DEPRESSION", "DIABETES"}
    assert {"CSMOKING", "BINGE", "LPA", "OBESITY", "SLEEP"}.issubset(context_measure_ids)
    assert set(SCENARIO_EDITABLE_COLUMNS).isdisjoint(
        {f"places_{spec.feature_prefix}_crude_prevalence" for spec in PLACES_CONTEXT_MEASURES}
    )


def test_build_places_county_context_table_pivots_crude_prevalence(tmp_path: Path) -> None:
    """County PLACES context should pivot selected crude prevalence measures to stable columns."""
    raw_path = tmp_path / "places_county_2025.csv"
    _write_places_raw_csv(raw_path)

    table = build_places_county_context_table(raw_path, release_year=2025)

    assert table["county_fips"].tolist() == ["06001", "06013"]
    assert table["release_year"].tolist() == [2025, 2025]
    assert table["year"].tolist() == [2023, 2023]
    assert table["places_estimate_year_min"].tolist() == [2022, 2022]
    assert table["places_estimate_year_max"].tolist() == [2023, 2023]
    assert table["places_short_sleep_duration_estimate_year"].tolist() == [2022, 2022]
    first = table.iloc[0]
    assert first["state_fips"] == "06"
    assert first["state_abbr"] == "CA"
    assert first["geography_name"] == "Alameda County, California"
    assert first["places_total_population"] == 1000
    assert first["places_total_pop_18plus"] == 800
    assert first["places_coronary_heart_disease_crude_prevalence"] == pytest.approx(5.0)
    assert first["places_coronary_heart_disease_crude_prevalence_low"] == pytest.approx(4.0)
    assert first["places_coronary_heart_disease_crude_prevalence_high"] == pytest.approx(6.0)
    assert first["places_current_smoking_crude_prevalence"] == pytest.approx(15.0)

    second = table.iloc[1]
    assert second["places_coronary_heart_disease_crude_prevalence"] == pytest.approx(9.0)


def test_build_places_tables_is_idempotent_and_writes_provenance(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The PLACES build CLI path should skip complete outputs and write provenance."""
    base_dir = tmp_path / "data"
    year = 2025
    _write_places_raw_csv(places_county_csv_path(base_dir, year=year))

    build_places_tables(base_dir=base_dir, years=[year], force=False, dry_run=False)
    build_places_tables(base_dir=base_dir, years=[year], force=False, dry_run=False)

    output_path = places_county_year_parquet(base_dir)
    assert output_path.exists()
    output = pd.read_parquet(output_path)
    assert set(output["release_year"].tolist()) == {year}
    assert "Skip build (exists)" in capsys.readouterr().out

    provenance_path = base_dir / "processed" / "provenance" / f"places_county_year_{year}.json"
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    assert provenance["dataset_name"] == "cdc_places_county_context"
    assert provenance["places_release_years"] == [year]
    assert "CHD" in provenance["places_measure_ids"]
    assert "source_registry_by_year" in provenance
    assert "not independent person-level labels" in provenance["places_context_caveat"]
