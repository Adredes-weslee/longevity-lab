"""Tests for EPA AirData CLI behavior."""

from __future__ import annotations

from pathlib import Path

import pandas as pd  # type: ignore[import-untyped]
import pytest

from longevity_lab.pipeline.build_epa_tables import main as build_epa_tables_main
from longevity_lab.pipeline.ingest import build_ingest_paths


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


def test_build_epa_tables_does_not_skip_when_missing_years(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """If output exists but does not contain the requested years, rebuild."""
    base_dir = tmp_path / "data"
    paths = build_ingest_paths(base_dir)

    for year in [2022, 2023]:
        _write_minimal_epa_csv(paths.epa_airdata_annual_aqi_csv(year), year=year)

    output_path = paths.epa_state_year_parquet()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([{"year": 2022, "state_fips": "06", "annual_aqi": 50}]).to_parquet(
        output_path,
        index=False,
    )

    build_epa_tables_main(["--base-dir", str(base_dir), "--years", "2022,2023"])

    out = pd.read_parquet(output_path)
    assert set(out["year"].tolist()) == {2022, 2023}

    captured = capsys.readouterr().out
    assert "Skip build" not in captured
