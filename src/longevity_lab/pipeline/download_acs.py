"""Download curated Census ACS 5-year context inputs."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Literal
from urllib.parse import urlencode

import pandas as pd  # type: ignore[import-untyped]

from longevity_lab.pipeline.common import (
    add_common_pipeline_args,
    collect_file_provenance,
    download_file,
    parse_years_from_args,
    require_columns,
)
from longevity_lab.pipeline.provenance import write_registry_provenance_json
from longevity_lab.pipeline.sources import load_data_source_registry

ACS_SOURCE_ID = "census_acs5_api_context"
ACS_GEOGRAPHIES: tuple[str, str] = ("state", "county")
ACS_API_MAX_GET_VARIABLES = 50
ACS_QUERY_VARIABLES: tuple[str, ...] = (
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
)


def acs_raw_dir(base_dir: Path, *, year: int) -> Path:
    """Return the raw ACS landing directory for `year`."""
    return base_dir / "external" / "acs" / "acs5" / str(year)


def acs_raw_json_path(
    base_dir: Path,
    *,
    year: int,
    geography: Literal["state", "county"] | str,
) -> Path:
    """Return the raw ACS API JSON path for a geography."""
    if geography not in ACS_GEOGRAPHIES:
        raise ValueError(f"Unsupported ACS geography: {geography!r}")
    return acs_raw_dir(base_dir, year=year) / f"acs5_{geography}_context.json"


def acs_api_url(
    *,
    year: int,
    geography: Literal["state", "county"] | str,
    api_key: str | None = None,
) -> str:
    """Return the first Census API URL for curated ACS context variables."""
    return acs_api_urls(year=year, geography=geography, api_key=api_key)[0]


def acs_api_urls(
    *,
    year: int,
    geography: Literal["state", "county"] | str,
    api_key: str | None = None,
) -> list[str]:
    """Return Census API URLs chunked under the API variable limit."""
    if geography not in ACS_GEOGRAPHIES:
        raise ValueError(f"Unsupported ACS geography: {geography!r}")

    urls: list[str] = []
    chunk_size = ACS_API_MAX_GET_VARIABLES - 1
    for start in range(0, len(ACS_QUERY_VARIABLES), chunk_size):
        variable_chunk = ACS_QUERY_VARIABLES[start : start + chunk_size]
        params = {
            "get": ",".join(("NAME", *variable_chunk)),
            "for": "state:*" if geography == "state" else "county:*",
        }
        if geography == "county":
            params["in"] = "state:*"
        if api_key:
            params["key"] = api_key
        urls.append(f"https://api.census.gov/data/{year}/acs/acs5?{urlencode(params)}")
    return urls


def _acs_raw_chunk_json_path(
    base_dir: Path,
    *,
    year: int,
    geography: Literal["state", "county"] | str,
    chunk_number: int,
) -> Path:
    """Return a temporary ACS API chunk path."""
    final_path = acs_raw_json_path(base_dir, year=year, geography=geography)
    return final_path.with_name(f"{final_path.stem}_part{chunk_number}.json")


def _read_api_json(path: Path) -> pd.DataFrame:
    """Read one Census API JSON response into a DataFrame."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list) or not payload:
        raise ValueError(f"Invalid ACS JSON payload: {path}")
    headers = [str(item) for item in payload[0]]
    return pd.DataFrame(payload[1:], columns=headers)


def merge_acs_json_chunks(
    chunk_paths: Sequence[Path],
    out_path: Path,
    *,
    geography: Literal["state", "county"] | str,
) -> None:
    """Merge chunked Census API JSON responses into one API-shaped JSON file."""
    if geography not in ACS_GEOGRAPHIES:
        raise ValueError(f"Unsupported ACS geography: {geography!r}")
    key_columns = ["NAME", "state"] if geography == "state" else ["NAME", "state", "county"]

    merged: pd.DataFrame | None = None
    value_columns: list[str] = []
    for chunk_path in chunk_paths:
        frame = _read_api_json(chunk_path)
        require_columns(actual=frame.columns, required=key_columns, context=f"ACS {geography}")
        for column in frame.columns:
            if column not in key_columns and column not in value_columns:
                value_columns.append(str(column))
        if merged is None:
            merged = frame.copy()
            continue
        new_columns = [
            column for column in frame.columns if column in key_columns or column not in merged
        ]
        merged = merged.merge(
            frame.loc[:, new_columns],
            on=key_columns,
            how="outer",
            validate="one_to_one",
        )

    if merged is None:
        raise ValueError("No ACS JSON chunks were provided.")
    ordered_columns = [*key_columns, *value_columns]
    merged = merged.loc[:, ordered_columns].sort_values(key_columns).reset_index(drop=True)
    merged = merged.astype(object).where(pd.notna(merged), None)
    payload = [ordered_columns, *merged.values.tolist()]

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload) + "\n", encoding="utf-8")


def _geographies_from_arg(value: str) -> list[str]:
    """Return one or both ACS geography names from a CLI option."""
    if value == "both":
        return list(ACS_GEOGRAPHIES)
    if value not in ACS_GEOGRAPHIES:
        raise ValueError(f"Unsupported ACS geography: {value!r}")
    return [value]


def download_acs(
    *,
    base_dir: Path,
    years: list[int],
    geography: str,
    api_key: str | None,
    force: bool,
    dry_run: bool,
) -> None:
    """Download curated ACS API JSON files for requested years and geography."""
    geographies = _geographies_from_arg(geography)
    provenance_dir = base_dir / "processed" / "provenance"
    source = load_data_source_registry().require(ACS_SOURCE_ID)

    for year in years:
        source.ensure_supported_year(year)
        for item in geographies:
            urls = acs_api_urls(year=year, geography=item, api_key=api_key)
            out_path = acs_raw_json_path(base_dir, year=year, geography=item)
            if out_path.exists() and not force:
                print(f"Skip download (exists): {out_path}")
            else:
                chunk_paths: list[Path] = []
                for index, url in enumerate(urls, start=1):
                    chunk_path = _acs_raw_chunk_json_path(
                        base_dir,
                        year=year,
                        geography=item,
                        chunk_number=index,
                    )
                    chunk_paths.append(chunk_path)
                    download_file(url, chunk_path, force=force, dry_run=dry_run)
                if not dry_run:
                    merge_acs_json_chunks(chunk_paths, out_path, geography=item)

            files = []
            if out_path.exists():
                files.append(collect_file_provenance(out_path, root=base_dir))
            write_registry_provenance_json(
                provenance_dir / f"census_acs5_{item}_context_raw_{year}.json",
                dataset_name=f"census_acs5_{item}_context_raw",
                dataset_version=str(year),
                source_ids=[ACS_SOURCE_ID],
                year=year,
                sources=urls,
                files=files,
                extra={"geography": item, "variables": list(ACS_QUERY_VARIABLES)},
                dry_run=dry_run,
            )


def main(argv: list[str] | None = None) -> None:
    """CLI entrypoint for downloading curated ACS context inputs."""
    parser = argparse.ArgumentParser(description="Download curated Census ACS 5-year context JSON.")
    add_common_pipeline_args(parser)
    parser.add_argument(
        "--geography",
        choices=("state", "county", "both"),
        default="both",
        help="ACS geography to download (default: both).",
    )
    parser.add_argument(
        "--api-key",
        default=None,
        help="Optional Census API key. Small curated queries usually work without one.",
    )
    args = parser.parse_args(argv)
    download_acs(
        base_dir=Path(args.base_dir),
        years=parse_years_from_args(args),
        geography=str(args.geography),
        api_key=args.api_key,
        force=bool(args.force),
        dry_run=bool(args.dry_run),
    )


if __name__ == "__main__":
    main()
