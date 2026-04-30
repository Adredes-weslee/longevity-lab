"""Integration tests for DuckDB views builder.

These tests use tiny local parquet files (no network, no large datasets).
"""

from __future__ import annotations

from pathlib import Path

import duckdb  # type: ignore[import-untyped]
import pandas as pd  # type: ignore[import-untyped]

from longevity_lab.pipeline.build_duckdb_views import build_duckdb_views


def _write_parquet(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False)


def test_build_duckdb_views_updates_existing_db(tmp_path: Path) -> None:
    """build_duckdb_views should refresh views even if the DB already exists."""
    base_dir = tmp_path / "data"

    brfss_path = base_dir / "processed" / "brfss" / "2023" / "brfss_person.parquet"
    integrated_path = (
        base_dir / "processed" / "integrated" / "2023" / "integrated_person_year.parquet"
    )
    epa_path = base_dir / "processed" / "epa_airdata" / "annual_aqi_state_year.parquet"

    _write_parquet(
        brfss_path,
        pd.DataFrame(
            [
                {
                    "year": 2023,
                    "state_fips": "01",
                    "age": 21,
                    "bmi": 25.0,
                    "smoker": False,
                    "alcohol_servings_per_week": 0,
                    "exercise_minutes_per_week": 150,
                }
            ]
        ),
    )
    _write_parquet(
        integrated_path,
        pd.DataFrame(
            [
                {
                    "year": 2023,
                    "state_fips": "01",
                    "annual_aqi": 45,
                }
            ]
        ),
    )
    _write_parquet(
        epa_path,
        pd.DataFrame(
            [
                {
                    "year": 2023,
                    "state_fips": "01",
                    "annual_aqi": 45,
                }
            ]
        ),
    )

    build_duckdb_views(base_dir=base_dir, years=[2023], force=False, dry_run=False)

    db_path = base_dir / "processed" / "longevity_lab.duckdb"
    assert db_path.exists()

    with duckdb.connect(str(db_path), read_only=True) as connection:
        assert connection.execute("SELECT COUNT(*) FROM v_brfss_person").fetchone() == (1,)

    _write_parquet(
        brfss_path,
        pd.DataFrame(
            [
                {
                    "year": 2023,
                    "state_fips": "01",
                    "age": 21,
                    "bmi": 25.0,
                    "smoker": False,
                    "alcohol_servings_per_week": 0,
                    "exercise_minutes_per_week": 150,
                },
                {
                    "year": 2023,
                    "state_fips": "06",
                    "age": 42,
                    "bmi": 30.0,
                    "smoker": True,
                    "alcohol_servings_per_week": 10,
                    "exercise_minutes_per_week": 60,
                },
            ]
        ),
    )

    build_duckdb_views(base_dir=base_dir, years=[2023], force=False, dry_run=False)

    with duckdb.connect(str(db_path), read_only=True) as connection:
        assert connection.execute("SELECT COUNT(*) FROM v_brfss_person").fetchone() == (2,)
