"""Download EPA AirData annual AQI and concentration files (raw)."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from longevity_lab.pipeline.common import (
    add_common_pipeline_args,
    collect_file_provenance,
    download_file,
    extract_zip,
    parse_years_from_args,
)
from longevity_lab.pipeline.ingest import build_ingest_paths
from longevity_lab.pipeline.provenance import write_registry_provenance_json
from longevity_lab.pipeline.sources import load_data_source_registry

_EPA_ANNUAL_AQI_SOURCE_ID = "epa_airdata_annual_aqi_by_county"
_EPA_ANNUAL_CONCENTRATION_SOURCE_ID = "epa_airdata_annual_conc_by_monitor"


def _annual_aqi_by_county_url(year: int) -> str:
    registry = load_data_source_registry()
    return registry.require(_EPA_ANNUAL_AQI_SOURCE_ID).download_url(year=year)


def _annual_conc_by_monitor_url(year: int) -> str:
    registry = load_data_source_registry()
    return registry.require(_EPA_ANNUAL_CONCENTRATION_SOURCE_ID).download_url(year=year)


def _annual_conc_by_monitor_zip_path(base_dir: Path, year: int) -> Path:
    return base_dir / "external" / "epa_airdata" / f"annual_conc_by_monitor_{year}.zip"


def _annual_conc_by_monitor_extract_dir(base_dir: Path, year: int) -> Path:
    return base_dir / "external" / "epa_airdata" / f"annual_conc_by_monitor_{year}"


def _normalize_extracted_csv(
    *,
    extract_dir: Path,
    expected_name: str,
    extracted_paths: list[Path],
    dry_run: bool,
) -> list[Path]:
    """Ensure expected AirData CSVs are available at the documented extract root."""
    expected_path = extract_dir / expected_name
    if dry_run:
        return extracted_paths

    candidate = next(
        (path for path in extracted_paths if path.is_file() and path.name == expected_name),
        None,
    )
    if candidate is None or not candidate.is_file():
        return extracted_paths
    if candidate.resolve() == expected_path.resolve():
        return extracted_paths

    expected_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(candidate, expected_path)
    return [*extracted_paths, expected_path]


def main(argv: list[str] | None = None) -> None:
    """CLI entrypoint for downloading EPA AirData annual zip(s)."""
    parser = argparse.ArgumentParser(
        description="Download EPA AirData annual AQI and concentration summaries."
    )
    add_common_pipeline_args(parser)
    args = parser.parse_args(argv)
    years = parse_years_from_args(args)
    paths = build_ingest_paths(Path(args.base_dir))

    for year in years:
        aqi_url = _annual_aqi_by_county_url(year)
        annual_conc_url = _annual_conc_by_monitor_url(year)

        aqi_zip_path = paths.epa_airdata_annual_aqi_zip(year)
        annual_conc_zip_path = _annual_conc_by_monitor_zip_path(paths.base_dir, year)

        download_file(aqi_url, aqi_zip_path, force=args.force, dry_run=args.dry_run)
        aqi_extracted = extract_zip(
            aqi_zip_path,
            paths.epa_airdata_annual_aqi_extract_dir(year),
            dry_run=args.dry_run,
        )

        download_file(
            annual_conc_url,
            annual_conc_zip_path,
            force=args.force,
            dry_run=args.dry_run,
        )
        annual_conc_extracted = extract_zip(
            annual_conc_zip_path,
            _annual_conc_by_monitor_extract_dir(paths.base_dir, year),
            dry_run=args.dry_run,
        )
        annual_conc_extracted = _normalize_extracted_csv(
            extract_dir=_annual_conc_by_monitor_extract_dir(paths.base_dir, year),
            expected_name=f"annual_conc_by_monitor_{year}.csv",
            extracted_paths=annual_conc_extracted,
            dry_run=args.dry_run,
        )

        provenance_path = paths.provenance_epa_airdata_annual_aqi_by_county(year)
        files = []
        if not args.dry_run:
            if aqi_zip_path.exists():
                files.append(
                    collect_file_provenance(aqi_zip_path, url=aqi_url, root=paths.base_dir)
                )
            if annual_conc_zip_path.exists():
                files.append(
                    collect_file_provenance(
                        annual_conc_zip_path,
                        url=annual_conc_url,
                        root=paths.base_dir,
                    )
                )
            for item in [*aqi_extracted, *annual_conc_extracted]:
                if item.is_file():
                    files.append(collect_file_provenance(item, root=paths.base_dir))
        write_registry_provenance_json(
            provenance_path,
            dataset_name="epa_airdata_annual_aqi_and_concentration",
            dataset_version=str(year),
            source_ids=[_EPA_ANNUAL_AQI_SOURCE_ID, _EPA_ANNUAL_CONCENTRATION_SOURCE_ID],
            year=year,
            sources=[aqi_url, annual_conc_url],
            files=files,
            extra={
                "annual_concentration_url": annual_conc_url,
                "annual_concentration_expected_file": f"annual_conc_by_monitor_{year}.csv",
                "pollutants": ["pm25", "ozone"],
            },
            dry_run=args.dry_run,
        )


if __name__ == "__main__":
    main()
