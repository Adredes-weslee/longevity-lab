"""Download CDC PLACES county Open Data CSV inputs."""

from __future__ import annotations

import argparse
from pathlib import Path

from longevity_lab.pipeline.common import (
    add_common_pipeline_args,
    collect_file_provenance,
    download_file,
    parse_years_from_args,
)
from longevity_lab.pipeline.provenance import write_registry_provenance_json
from longevity_lab.pipeline.sources import load_data_source_registry

PLACES_SOURCE_ID = "cdc_places_county_opendata"
PLACES_CONTEXT_CAVEAT = (
    "CDC PLACES provides modeled aggregate geography context and external reasonableness "
    "checks; it is not independent person-level labels for Longevity Lab models."
)


def places_county_csv_url(year: int) -> str:
    """Return the official public CDC PLACES county CSV download URL."""
    return load_data_source_registry().require(PLACES_SOURCE_ID).download_url(year=year)


def places_raw_dir(base_dir: Path, *, year: int) -> Path:
    """Return the raw PLACES county landing directory for a release year."""
    return base_dir / "external" / "places" / "county" / str(year)


def places_county_csv_path(base_dir: Path, *, year: int) -> Path:
    """Return the raw PLACES county CSV path for a release year."""
    return places_raw_dir(base_dir, year=year) / f"places_county_{year}.csv"


def download_places(
    *,
    base_dir: Path,
    years: list[int],
    force: bool,
    dry_run: bool,
) -> None:
    """Download CDC PLACES county CSVs for requested release years."""
    provenance_dir = base_dir / "processed" / "provenance"
    for year in years:
        url = places_county_csv_url(year)
        out_path = places_county_csv_path(base_dir, year=year)
        download_file(url, out_path, force=force, dry_run=dry_run)

        files = []
        if out_path.exists():
            files.append(collect_file_provenance(out_path, url=url, root=base_dir))
        write_registry_provenance_json(
            provenance_dir / f"cdc_places_county_raw_{year}.json",
            dataset_name="cdc_places_county_raw",
            dataset_version=str(year),
            source_ids=[PLACES_SOURCE_ID],
            year=year,
            sources=[url],
            files=files,
            extra={"places_context_caveat": PLACES_CONTEXT_CAVEAT},
            dry_run=dry_run,
        )


def main(argv: list[str] | None = None) -> None:
    """CLI entrypoint for downloading CDC PLACES county CSVs."""
    parser = argparse.ArgumentParser(description="Download CDC PLACES county Open Data CSV.")
    add_common_pipeline_args(parser)
    args = parser.parse_args(argv)
    download_places(
        base_dir=Path(args.base_dir),
        years=parse_years_from_args(args),
        force=bool(args.force),
        dry_run=bool(args.dry_run),
    )


if __name__ == "__main__":
    main()
