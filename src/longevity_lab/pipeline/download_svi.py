"""Download CDC/ATSDR SVI U.S. county CSV inputs."""

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

SVI_SOURCE_ID = "cdc_atsdr_svi_us_county_csv"


def svi_county_csv_url(year: int) -> str:
    """Return the CDC/ATSDR SVI U.S. county CSV URL for `year`."""
    return load_data_source_registry().require(SVI_SOURCE_ID).download_url(year=year)


def svi_raw_dir(base_dir: Path, *, year: int) -> Path:
    """Return the raw SVI landing directory for `year`."""
    return base_dir / "external" / "svi" / str(year)


def svi_county_csv_path(base_dir: Path, *, year: int) -> Path:
    """Return the raw SVI county CSV path for `year`."""
    return svi_raw_dir(base_dir, year=year) / f"SVI_{year}_US_county.csv"


def download_svi(
    *,
    base_dir: Path,
    years: list[int],
    force: bool,
    dry_run: bool,
) -> None:
    """Download CDC/ATSDR SVI county CSVs for requested years."""
    provenance_dir = base_dir / "processed" / "provenance"
    for year in years:
        url = svi_county_csv_url(year)
        out_path = svi_county_csv_path(base_dir, year=year)
        download_file(url, out_path, force=force, dry_run=dry_run)

        files = []
        if out_path.exists():
            files.append(collect_file_provenance(out_path, url=url, root=base_dir))
        write_registry_provenance_json(
            provenance_dir / f"cdc_atsdr_svi_us_county_raw_{year}.json",
            dataset_name="cdc_atsdr_svi_us_county_raw",
            dataset_version=str(year),
            source_ids=[SVI_SOURCE_ID],
            year=year,
            sources=[url],
            files=files,
            dry_run=dry_run,
        )


def main(argv: list[str] | None = None) -> None:
    """CLI entrypoint for downloading CDC/ATSDR SVI county CSVs."""
    parser = argparse.ArgumentParser(description="Download CDC/ATSDR SVI U.S. county CSV.")
    add_common_pipeline_args(parser)
    args = parser.parse_args(argv)
    download_svi(
        base_dir=Path(args.base_dir),
        years=parse_years_from_args(args),
        force=bool(args.force),
        dry_run=bool(args.dry_run),
    )


if __name__ == "__main__":
    main()
