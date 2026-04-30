"""Canonical dataset directory layout for pipeline ingest steps.

The pipeline expects a stable, year-aware directory layout rooted at a "base
data dir" (default: `data/`). Individual pipeline steps (download/build/integrate)
should import and use this module so path conventions live in one place.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class IngestPaths:
    """Typed path builder for pipeline dataset inputs/outputs."""

    base_dir: Path
    external_dir: Path
    processed_dir: Path
    provenance_dir: Path
    duckdb_path: Path

    @property
    def raw_dir(self) -> Path:
        """Alias for `external_dir` (raw assets live under `external/`)."""
        return self.external_dir

    def brfss_raw_dir(self, year: int) -> Path:
        """Return the BRFSS raw asset directory for the given year."""
        return self.external_dir / "brfss" / str(year)

    def brfss_processed_dir(self, year: int) -> Path:
        """Return the BRFSS processed output directory for the given year."""
        return self.processed_dir / "brfss" / str(year)

    def brfss_person_parquet(self, year: int) -> Path:
        """Return the processed BRFSS person parquet output path for the given year."""
        return self.brfss_processed_dir(year) / "brfss_person.parquet"

    def epa_airdata_raw_dir(self) -> Path:
        """Return the EPA AirData raw asset directory."""
        return self.external_dir / "epa_airdata"

    def epa_airdata_annual_aqi_zip(self, year: int) -> Path:
        """Return the EPA AirData annual AQI-by-county zip path for the given year."""
        return self.epa_airdata_raw_dir() / f"annual_aqi_by_county_{year}.zip"

    def epa_airdata_annual_aqi_extract_dir(self, year: int) -> Path:
        """Return the EPA AirData extraction directory for the given year."""
        return self.epa_airdata_raw_dir() / f"annual_aqi_by_county_{year}"

    def epa_airdata_annual_aqi_csv(self, year: int) -> Path:
        """Return the EPA AirData annual AQI-by-county CSV path for the given year."""
        return self.epa_airdata_annual_aqi_extract_dir(year) / f"annual_aqi_by_county_{year}.csv"

    def epa_processed_dir(self) -> Path:
        """Return the EPA processed output directory."""
        return self.processed_dir / "epa_airdata"

    def epa_state_year_parquet(self) -> Path:
        """Return the processed EPA state-year parquet output path."""
        return self.epa_processed_dir() / "annual_aqi_state_year.parquet"

    def integrated_processed_dir(self, year: int) -> Path:
        """Return the integrated parquet output directory for the given year."""
        return self.processed_dir / "integrated" / str(year)

    def integrated_person_year_parquet(self, year: int) -> Path:
        """Return the processed integrated person-year parquet output path for the given year."""
        return self.integrated_processed_dir(year) / "integrated_person_year.parquet"

    def provenance_brfss_raw(self, year: int) -> Path:
        """Return the expected provenance JSON path for BRFSS raw downloads."""
        return self.provenance_dir / f"brfss_raw_{year}.json"

    def provenance_brfss_person(self, year: int) -> Path:
        """Return the expected provenance JSON path for BRFSS processed person output."""
        return self.provenance_dir / f"brfss_person_{year}.json"

    def provenance_epa_airdata_annual_aqi_by_county(self, year: int) -> Path:
        """Return the expected provenance JSON path for the EPA raw download."""
        return self.provenance_dir / f"epa_airdata_annual_aqi_by_county_{year}.json"

    def provenance_epa_airdata_state_year(self, years: Sequence[int]) -> Path:
        """Return the expected provenance JSON path for the EPA processed state-year table."""
        years_str = "_".join(str(year) for year in years)
        return self.provenance_dir / f"epa_airdata_annual_aqi_state_year_{years_str}.json"

    def provenance_integrated_person_year(self, year: int) -> Path:
        """Return the expected provenance JSON path for the integrated person-year output."""
        return self.provenance_dir / f"integrated_person_year_{year}.json"


def build_ingest_paths(base_dir: Path) -> IngestPaths:
    """Return the canonical ingest path layout rooted at `base_dir`."""
    external_dir = base_dir / "external"
    processed_dir = base_dir / "processed"
    provenance_dir = processed_dir / "provenance"
    return IngestPaths(
        base_dir=base_dir,
        external_dir=external_dir,
        processed_dir=processed_dir,
        provenance_dir=provenance_dir,
        duckdb_path=processed_dir / "longevity_lab.duckdb",
    )


def build_paths(base_dir: Path) -> IngestPaths:
    """Backwards-compatible alias for `build_ingest_paths`."""
    return build_ingest_paths(base_dir)


def main() -> None:
    """Print the expected dataset directory layout (debug helper)."""
    paths = build_ingest_paths(Path("data"))
    print("Ingest path layout is ready.")
    print(f"Base data dir: {paths.base_dir}")
    print(f"External dir: {paths.external_dir}")
    print(f"Processed dir: {paths.processed_dir}")
    print(f"Provenance dir: {paths.provenance_dir}")
    print(f"DuckDB path: {paths.duckdb_path}")


if __name__ == "__main__":
    main()
