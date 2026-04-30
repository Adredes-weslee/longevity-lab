"""Shared helpers for pipeline CLIs (download, provenance, validation)."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import shutil
import time
import urllib.error
import urllib.request
import zipfile
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Any


@dataclass(frozen=True, slots=True)
class FileProvenance:
    """Provenance metadata for one local file."""

    path: str
    bytes: int
    sha256: str
    url: str | None = None


def default_data_dir() -> Path:
    """Return the repo-root data directory used by pipeline CLIs."""
    return Path(__file__).resolve().parents[3] / "data"


def add_common_pipeline_args(
    parser: argparse.ArgumentParser, *, require_years: bool = True
) -> None:
    """Add standard pipeline CLI flags to an argparse parser.

    Conventions:
    - `--base-dir`: base data directory (default: repo-root `data/`)
    - `--year` or `--years`: choose dataset year(s)
    - `--force`: overwrite/rebuild even if outputs exist
    - `--dry-run`: print actions but do not write files
    """
    base_dir = default_data_dir()
    parser.add_argument(
        "--base-dir",
        type=Path,
        default=base_dir,
        help=f"Base data directory (default: {base_dir}).",
    )
    year_group = parser.add_mutually_exclusive_group(required=require_years)
    year_group.add_argument("--year", type=int, help="Single year to process.")
    year_group.add_argument(
        "--years",
        type=str,
        help="Comma-separated years to process, e.g. 2021,2022,2023.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite/rebuild even if outputs already exist.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print actions but do not write files.",
    )


def parse_years_from_args(args: argparse.Namespace) -> list[int]:
    """Return a sorted list of unique years from parsed args."""
    raw_years: list[int]
    if args.year is not None:
        raw_years = [int(args.year)]
    elif args.years is not None:
        raw_years = parse_years_csv(str(args.years))
    else:
        raw_years = []
    years = sorted(set(raw_years))
    if not years:
        raise ValueError("No year(s) provided. Use --year or --years.")
    return years


def parse_years_csv(value: str) -> list[int]:
    """Parse a comma-separated year list into integers."""
    items = [part.strip() for part in value.split(",") if part.strip()]
    years: list[int] = []
    for item in items:
        try:
            years.append(int(item))
        except ValueError as exc:  # pragma: no cover
            raise ValueError(f"Invalid year: {item!r}") from exc
    return years


def sha256_file(path: Path) -> str:
    """Return the SHA256 hex digest of a file."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def collect_file_provenance(
    path: Path,
    *,
    url: str | None = None,
    root: Path | None = None,
) -> FileProvenance:
    """Collect byte size and SHA256 for a local file."""
    rel = path
    if root is not None:
        rel = path.relative_to(root)
    rel_str = rel.as_posix()
    return FileProvenance(
        path=rel_str,
        bytes=path.stat().st_size,
        sha256=sha256_file(path),
        url=url,
    )


def write_provenance_json(
    out_path: Path,
    *,
    dataset_name: str,
    dataset_version: str,
    sources: Sequence[str],
    files: Sequence[FileProvenance],
    extra: dict[str, Any] | None = None,
    dry_run: bool = False,
) -> None:
    """Write a machine-readable provenance JSON document."""
    payload: dict[str, Any] = {
        "dataset_name": dataset_name,
        "dataset_version": dataset_version,
        "retrieved_at": dt.datetime.now(dt.UTC).isoformat(),
        "sources": list(sources),
        "files": [asdict(item) for item in files],
    }
    if extra:
        payload.update(extra)

    if dry_run:
        print(f"DRY RUN: write provenance -> {out_path}")
        return

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def download_file(
    url: str,
    dest_path: Path,
    *,
    force: bool,
    dry_run: bool,
    retries: int = 3,
    timeout_seconds: float = 60.0,
) -> None:
    """Download a URL to a local path with basic retries."""
    if dest_path.exists() and not force:
        print(f"Skip download (exists): {dest_path}")
        return

    print(f"Download: {url} -> {dest_path}")
    if dry_run:
        print("DRY RUN: download skipped")
        return

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = dest_path.with_suffix(dest_path.suffix + ".part")

    request = urllib.request.Request(
        url,
        headers={"User-Agent": "longevity-lab-pipeline/0.1"},
    )

    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310
                with tmp_path.open("wb") as handle:
                    while True:
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        handle.write(chunk)
            tmp_path.replace(dest_path)
            return
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = exc
            try:
                tmp_path.unlink()
            except FileNotFoundError:
                pass
            except OSError:
                pass
            if attempt >= retries:
                break
            backoff_seconds = min(2**attempt, 10)
            print(
                f"Download failed (attempt {attempt}/{retries}): {exc}. "
                f"Retrying in {backoff_seconds}s."
            )
            time.sleep(backoff_seconds)

    raise RuntimeError(f"Failed to download after {retries} attempts: {url}") from last_error


def extract_zip(
    zip_path: Path,
    dest_dir: Path,
    *,
    dry_run: bool,
) -> list[Path]:
    """Extract a zip file into a directory and return extracted paths."""
    print(f"Extract: {zip_path} -> {dest_dir}")
    if dry_run:
        print("DRY RUN: extract skipped")
        return []

    dest_dir.mkdir(parents=True, exist_ok=True)
    extracted: list[Path] = []

    dest_dir_resolved = dest_dir.resolve()

    def safe_member_path(member_name: str) -> Path:
        normalized = member_name.replace("\\", "/")
        pure = PurePosixPath(normalized)
        if pure.is_absolute() or not pure.parts:
            raise ValueError(f"Unsafe zip member path: {member_name!r}")
        first = pure.parts[0]
        if len(first) >= 2 and first[1] == ":":
            raise ValueError(f"Unsafe zip member path: {member_name!r}")

        target_rel = dest_dir / Path(*pure.parts)
        target = target_rel.resolve()
        try:
            relative = target.relative_to(dest_dir_resolved)
        except ValueError as exc:
            raise ValueError(f"Unsafe zip member path: {member_name!r}") from exc
        return dest_dir / relative

    with zipfile.ZipFile(zip_path) as archive:
        for info in archive.infolist():
            target_path = safe_member_path(info.filename)
            if info.is_dir():
                target_path.mkdir(parents=True, exist_ok=True)
                extracted.append(target_path)
                continue
            target_path.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as source, target_path.open("wb") as handle:
                shutil.copyfileobj(source, handle)
            extracted.append(target_path)
    return extracted


def require_columns(
    *,
    actual: Iterable[str],
    required: Sequence[str],
    context: str,
) -> None:
    """Raise if any required columns are missing from an iterable of column names."""
    actual_set = set(actual)
    missing = [name for name in required if name not in actual_set]
    if missing:
        raise ValueError(f"Missing required columns for {context}: {missing}")
