"""Download EPA AirData annual AQI files (raw)."""

from __future__ import annotations

import argparse
from pathlib import Path

from longevity_lab.pipeline.common import (
    add_common_pipeline_args,
    collect_file_provenance,
    download_file,
    extract_zip,
    parse_years_from_args,
    write_provenance_json,
)
from longevity_lab.pipeline.ingest import build_ingest_paths


def _annual_aqi_by_county_url(year: int) -> str:
    return f"https://aqs.epa.gov/aqsweb/airdata/annual_aqi_by_county_{year}.zip"


def main(argv: list[str] | None = None) -> None:
    """CLI entrypoint for downloading EPA AirData annual AQI zip(s)."""
    parser = argparse.ArgumentParser(description="Download EPA AirData annual AQI by county.")
    add_common_pipeline_args(parser)
    args = parser.parse_args(argv)
    years = parse_years_from_args(args)
    paths = build_ingest_paths(Path(args.base_dir))

    for year in years:
        url = _annual_aqi_by_county_url(year)
        zip_path = paths.epa_airdata_annual_aqi_zip(year)
        download_file(url, zip_path, force=args.force, dry_run=args.dry_run)
        extracted = extract_zip(
            zip_path,
            paths.epa_airdata_annual_aqi_extract_dir(year),
            dry_run=args.dry_run,
        )

        provenance_path = paths.provenance_epa_airdata_annual_aqi_by_county(year)
        files = []
        if not args.dry_run and zip_path.exists():
            files.append(collect_file_provenance(zip_path, url=url, root=paths.base_dir))
            for item in extracted:
                if item.is_file():
                    files.append(collect_file_provenance(item, root=paths.base_dir))
        write_provenance_json(
            provenance_path,
            dataset_name="epa_airdata_annual_aqi_by_county",
            dataset_version=str(year),
            sources=[url],
            files=files,
            dry_run=args.dry_run,
        )


if __name__ == "__main__":
    main()
