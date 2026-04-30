"""Build a local DuckDB database and stable views from processed parquet outputs.

This is a convenience layer for downstream components (modeling/API/UI) so they can
query a stable set of views without needing to know per-year parquet paths.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import duckdb  # type: ignore[import-untyped]

from longevity_lab.pipeline.common import add_common_pipeline_args, parse_years_from_args
from longevity_lab.pipeline.ingest import IngestPaths, build_ingest_paths


def _sql_quote(value: str) -> str:
    escaped = value.replace("'", "''")
    return f"'{escaped}'"


def _sql_list_literal(values: list[str]) -> str:
    return "[" + ", ".join(_sql_quote(value) for value in values) + "]"


def _brfss_paths(paths: IngestPaths, years: list[int] | None) -> list[Path]:
    if years is None:
        return sorted((paths.processed_dir / "brfss").glob("*/brfss_person.parquet"))
    return [paths.brfss_person_parquet(year) for year in years]


def _integrated_paths(paths: IngestPaths, years: list[int] | None) -> list[Path]:
    if years is None:
        return sorted((paths.processed_dir / "integrated").glob("*/integrated_person_year.parquet"))
    return [paths.integrated_person_year_parquet(year) for year in years]


def _require_files(paths: list[Path], *, context: str) -> None:
    missing = [str(path) for path in paths if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Missing required files for {context}: {missing}")


def build_duckdb_views(
    *,
    base_dir: Path,
    years: list[int] | None,
    force: bool,
    dry_run: bool,
) -> None:
    """Create a DuckDB file and stable views for downstream usage."""
    paths = build_ingest_paths(base_dir)
    db_path = paths.duckdb_path
    brfss_paths = _brfss_paths(paths, years)
    integrated_paths = _integrated_paths(paths, years)
    epa_path = paths.epa_state_year_parquet()

    if not brfss_paths:
        raise FileNotFoundError("No BRFSS parquet files found under data/processed/brfss/.")
    if not integrated_paths:
        raise FileNotFoundError(
            "No integrated parquet files found under data/processed/integrated/."
        )
    _require_files(brfss_paths, context="BRFSS")
    _require_files(integrated_paths, context="integrated")
    if not epa_path.exists():
        raise FileNotFoundError(f"Missing EPA parquet file: {epa_path}")

    exists = db_path.exists()
    verb = "Update" if exists and not force else "Build"
    print(f"{verb} DuckDB views: {db_path}")
    if dry_run:
        print("DRY RUN: DuckDB write skipped")
        return

    db_path.parent.mkdir(parents=True, exist_ok=True)
    if force and exists:
        db_path.unlink()
    connection = duckdb.connect(str(db_path))
    try:
        connection.execute("PRAGMA enable_object_cache;")

        connection.execute("DROP VIEW IF EXISTS v_brfss_person;")
        connection.execute("DROP VIEW IF EXISTS v_epa_aqi_state_year;")
        connection.execute("DROP VIEW IF EXISTS v_integrated_person_year;")

        brfss_files = [path.as_posix() for path in brfss_paths]
        integrated_files = [path.as_posix() for path in integrated_paths]
        epa_file = epa_path.as_posix()

        if years is None:
            brfss_source = (paths.processed_dir / "brfss" / "*" / "brfss_person.parquet").as_posix()
            integrated_source = (
                paths.processed_dir / "integrated" / "*" / "integrated_person_year.parquet"
            ).as_posix()
            brfss_relation = f"read_parquet({_sql_quote(brfss_source)})"
            integrated_relation = f"read_parquet({_sql_quote(integrated_source)})"
        else:
            brfss_relation = f"read_parquet({_sql_list_literal(brfss_files)})"
            integrated_relation = f"read_parquet({_sql_list_literal(integrated_files)})"

        epa_relation = f"read_parquet({_sql_quote(epa_file)})"

        connection.execute(f"CREATE VIEW v_brfss_person AS SELECT * FROM {brfss_relation};")
        connection.execute(f"CREATE VIEW v_epa_aqi_state_year AS SELECT * FROM {epa_relation};")
        connection.execute(
            f"CREATE VIEW v_integrated_person_year AS SELECT * FROM {integrated_relation};"
        )

        brfss_row = connection.execute("SELECT COUNT(*) FROM v_brfss_person").fetchone()
        epa_row = connection.execute("SELECT COUNT(*) FROM v_epa_aqi_state_year").fetchone()
        integrated_row = connection.execute(
            "SELECT COUNT(*) FROM v_integrated_person_year"
        ).fetchone()

        if brfss_row is None or epa_row is None or integrated_row is None:  # pragma: no cover
            raise RuntimeError("DuckDB COUNT(*) query unexpectedly returned no rows.")

        brfss_count = int(brfss_row[0])
        epa_count = int(epa_row[0])
        integrated_count = int(integrated_row[0])

        print("View row counts:")
        print(f"  v_brfss_person: {brfss_count:,}")
        print(f"  v_epa_aqi_state_year: {epa_count:,}")
        print(f"  v_integrated_person_year: {integrated_count:,}")
    finally:
        connection.close()


def main(argv: list[str] | None = None) -> None:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description="Build DuckDB views from processed parquet files.")
    add_common_pipeline_args(parser, require_years=False)
    parser.add_argument(
        "--years-only",
        action="store_true",
        help="Limit views to the supplied --year/--years only (otherwise defaults to all files).",
    )
    args = parser.parse_args(argv)

    years: list[int] | None = None
    if args.years_only or args.year or args.years:
        try:
            years = parse_years_from_args(args)
        except ValueError as exc:
            parser.error(str(exc))

    build_duckdb_views(
        base_dir=Path(args.base_dir),
        years=years,
        force=bool(args.force),
        dry_run=bool(args.dry_run),
    )


if __name__ == "__main__":
    main()
