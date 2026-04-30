"""Download BRFSS annual microdata and codebook (CDC official)."""

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


def _brfss_urls(year: int) -> tuple[str, str]:
    """Return (microdata_zip_url, codebook_zip_url) for a supported year."""
    if year != 2023:
        raise NotImplementedError(
            f"BRFSS download is pinned to 2023 for v1. Unsupported year: {year}."
        )
    microdata = "https://www.cdc.gov/brfss/annual_data/2023/files/LLCP2023XPT.zip"
    codebook = "https://www.cdc.gov/brfss/annual_data/2023/zip/codebook23_llcp-v2-508.zip"
    return microdata, codebook


def _ensure_canonical_xpt_name(raw_dir: Path, *, year: int) -> Path:
    """Return the canonical local XPT path, normalizing trailing-space variants.

    The CDC zip currently contains `LLCP2023.XPT ` with a trailing space in the
    member name. Some environments materialize that name as-is, while others
    trim the trailing space during extraction. Keep the local filename stable as
    `LLCP{year}.XPT` for downstream pipeline steps and provenance.
    """
    canonical_path = raw_dir / f"LLCP{year}.XPT"
    if canonical_path.exists():
        return canonical_path

    candidates = [
        path
        for path in raw_dir.iterdir()
        if path.is_file() and path.name.rstrip() == canonical_path.name
    ]
    if not candidates:
        raise FileNotFoundError(f"Missing expected XPT after extract: {canonical_path}")
    if len(candidates) > 1:
        candidate_text = ", ".join(str(path) for path in sorted(candidates))
        raise FileExistsError(
            f"Multiple BRFSS XPT candidates map to the canonical name {canonical_path.name}: "
            f"{candidate_text}"
        )

    candidate = candidates[0]
    candidate.replace(canonical_path)
    return canonical_path


def download_brfss(
    *,
    base_dir: Path,
    years: list[int],
    force: bool,
    dry_run: bool,
) -> None:
    """Download BRFSS raw assets into `data/external/brfss/<year>/`."""
    paths = build_ingest_paths(base_dir)
    for year in years:
        microdata_url, codebook_url = _brfss_urls(year)

        raw_dir = paths.brfss_raw_dir(year)
        microdata_zip = raw_dir / f"LLCP{year}XPT.zip"
        codebook_zip = raw_dir / "codebook23_llcp-v2-508.zip"
        codebook_dir = raw_dir / "codebook"

        download_file(microdata_url, microdata_zip, force=force, dry_run=dry_run)
        extract_zip(microdata_zip, raw_dir, dry_run=dry_run)

        download_file(codebook_url, codebook_zip, force=force, dry_run=dry_run)
        extract_zip(codebook_zip, codebook_dir, dry_run=dry_run)

        provenance_path = paths.provenance_brfss_raw(year)
        if dry_run:
            write_provenance_json(
                provenance_path,
                dataset_name="brfss_raw",
                dataset_version=str(year),
                sources=[microdata_url, codebook_url],
                files=[],
                dry_run=True,
            )
            continue

        expected_xpt = _ensure_canonical_xpt_name(raw_dir, year=year)

        files = [
            collect_file_provenance(microdata_zip, url=microdata_url, root=base_dir),
            collect_file_provenance(expected_xpt, root=base_dir),
            collect_file_provenance(codebook_zip, url=codebook_url, root=base_dir),
        ]
        write_provenance_json(
            provenance_path,
            dataset_name="brfss_raw",
            dataset_version=str(year),
            sources=[microdata_url, codebook_url],
            files=files,
        )


def main(argv: list[str] | None = None) -> None:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(
        description="Download BRFSS annual microdata + codebook (CDC official)."
    )
    add_common_pipeline_args(parser)
    args = parser.parse_args(argv)

    years = parse_years_from_args(args)
    download_brfss(
        base_dir=Path(args.base_dir),
        years=years,
        force=bool(args.force),
        dry_run=bool(args.dry_run),
    )


if __name__ == "__main__":
    main()
