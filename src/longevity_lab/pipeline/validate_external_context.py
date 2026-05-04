"""Compare aggregate model risk patterns with CDC PLACES context estimates."""

from __future__ import annotations

import argparse
import datetime as dt
import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import pandas as pd  # type: ignore[import-untyped]

from longevity_lab.pipeline.build_places_tables import (
    PLACES_CONDITION_MEASURES,
    places_county_year_parquet,
)
from longevity_lab.pipeline.common import (
    FileProvenance,
    add_common_pipeline_args,
    collect_file_provenance,
    parse_years_from_args,
    require_columns,
    write_provenance_json,
)
from longevity_lab.pipeline.download_places import (
    PLACES_CONTEXT_CAVEAT,
    PLACES_SOURCE_ID,
    places_county_csv_url,
)
from longevity_lab.pipeline.provenance import registry_provenance_extra
from longevity_lab.pipeline.sources import load_data_source_registry

EXTERNAL_VALIDATION_CAVEAT = PLACES_CONTEXT_CAVEAT
VALIDATION_OUTPUT_DIR = "validation"
_MODEL_PROBABILITY_COLUMN = "mean_predicted_probability"
_REPORT_COLUMNS = [
    "condition_id",
    "places_measure_id",
    "geography_level",
    "release_year",
    "places_estimate_year",
    "state_fips",
    "county_fips",
    "geography_name",
    "n_model_rows",
    "model_mean_predicted_probability",
    "places_crude_prevalence",
    "places_crude_prevalence_probability",
    "absolute_difference",
    "relative_difference",
    "comparison_direction",
    "places_reference_kind",
    "places_is_model_based_context",
]


def places_external_validation_report_json_path(base_dir: Path, *, places_year: int) -> Path:
    """Return the external validation JSON report path."""
    return (
        base_dir
        / "processed"
        / VALIDATION_OUTPUT_DIR
        / f"places_external_context_validation_{places_year}.json"
    )


def places_external_validation_report_csv_path(base_dir: Path, *, places_year: int) -> Path:
    """Return the external validation CSV report path."""
    return (
        base_dir
        / "processed"
        / VALIDATION_OUTPUT_DIR
        / f"places_external_context_validation_{places_year}.csv"
    )


def provenance_external_validation_path(base_dir: Path, *, places_year: int) -> Path:
    """Return the external validation provenance JSON path."""
    return (
        base_dir
        / "processed"
        / "provenance"
        / f"places_external_context_validation_{places_year}.json"
    )


def _read_table(path: Path) -> pd.DataFrame:
    """Read a CSV, JSON, or Parquet table from disk."""
    suffix = path.suffix.casefold()
    if suffix == ".parquet":
        return pd.read_parquet(path)
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows = payload["rows"] if isinstance(payload, dict) and "rows" in payload else payload
        return pd.DataFrame(rows)
    raise ValueError(f"Unsupported table format for {path}. Use CSV, JSON, or Parquet.")


def _clean_fips_series(series: pd.Series, width: int) -> pd.Series:
    """Return zero-padded FIPS text while preserving missing values."""
    cleaned = series.astype("string").str.replace(r"\.0$", "", regex=True).str.zfill(width)
    return cleaned.mask(series.isna())


def _model_geography_level(frame: pd.DataFrame) -> str:
    if "county_fips" in frame.columns and frame["county_fips"].notna().any():
        return "county"
    if "state_fips" in frame.columns and frame["state_fips"].notna().any():
        return "state"
    return "national"


def _geography_columns(level: str) -> list[str]:
    if level == "county":
        return ["state_fips", "county_fips"]
    if level == "state":
        return ["state_fips"]
    if level == "national":
        return []
    raise ValueError(f"Unsupported geography level: {level!r}")


def _weighted_mean(values: pd.Series, weights: pd.Series | None = None) -> float | None:
    numeric_values = pd.to_numeric(values, errors="coerce")
    if weights is None:
        valid = numeric_values.notna()
        return float(numeric_values.loc[valid].mean()) if bool(valid.any()) else None
    numeric_weights = pd.to_numeric(weights, errors="coerce")
    valid = numeric_values.notna() & numeric_weights.notna() & numeric_weights.gt(0)
    if not bool(valid.any()):
        return None
    weighted_sum = (numeric_values.loc[valid] * numeric_weights.loc[valid]).sum()
    weight_total = numeric_weights.loc[valid].sum()
    return float(weighted_sum / weight_total)


def _direction(value: float | None) -> str | None:
    if value is None or pd.isna(value):
        return None
    if abs(value) < 1e-12:
        return "aligned"
    return "model_higher" if value > 0 else "model_lower"


def _finalize_model_frame(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    require_columns(actual=out.columns, required=["condition_id"], context="model aggregates")
    if "state_fips" in out.columns:
        out["state_fips"] = _clean_fips_series(out["state_fips"], 2)
    if "county_fips" in out.columns:
        out["county_fips"] = _clean_fips_series(out["county_fips"], 5)
        if "state_fips" not in out.columns:
            out["state_fips"] = out["county_fips"].astype("string").str.slice(0, 2)

    if _MODEL_PROBABILITY_COLUMN not in out.columns:
        require_columns(
            actual=out.columns,
            required=["predicted_probability"],
            context="model prediction rows",
        )
        out[_MODEL_PROBABILITY_COLUMN] = pd.to_numeric(
            out["predicted_probability"],
            errors="coerce",
        )
    out[_MODEL_PROBABILITY_COLUMN] = pd.to_numeric(out[_MODEL_PROBABILITY_COLUMN], errors="coerce")
    has_raw_predictions = "predicted_probability" in out.columns
    if "n_model_rows" not in out.columns:
        out["n_model_rows"] = 1
    out["n_model_rows"] = pd.to_numeric(out["n_model_rows"], errors="coerce").fillna(1)
    if has_raw_predictions and "survey_weight" in out.columns:
        out["_model_weight"] = (
            pd.to_numeric(out["survey_weight"], errors="coerce")
            .where(lambda values: values > 0)
            .fillna(1.0)
        )
    else:
        out["_model_weight"] = out["n_model_rows"]
    return out


def normalize_model_aggregates(model_aggregates: pd.DataFrame) -> pd.DataFrame:
    """Normalize model prediction rows or aggregate rows into comparable geography means."""
    frame = _finalize_model_frame(model_aggregates)
    if "geography_level" in frame.columns:
        levels = [str(value) for value in frame["geography_level"].dropna().unique().tolist()]
    else:
        levels = [_model_geography_level(frame)]

    rows: list[dict[str, Any]] = []
    for level in levels:
        level_frame = (
            frame
            if "geography_level" not in frame.columns
            else frame.loc[frame["geography_level"].astype(str) == level]
        )
        group_columns = ["condition_id", *_geography_columns(level)]
        for keys, group in level_frame.groupby(group_columns, dropna=False):
            key_values = keys if isinstance(keys, tuple) else (keys,)
            row: dict[str, Any] = {
                "condition_id": str(key_values[0]),
                "geography_level": level,
                "n_model_rows": int(pd.to_numeric(group["n_model_rows"], errors="coerce").sum()),
            }
            for column, value in zip(group_columns[1:], key_values[1:], strict=True):
                row[column] = None if pd.isna(value) else str(value)
            row["model_mean_predicted_probability"] = _weighted_mean(
                group[_MODEL_PROBABILITY_COLUMN],
                group["_model_weight"],
            )
            rows.append(row)
    return pd.DataFrame(rows)


def _places_condition_rows(places_context: pd.DataFrame) -> pd.DataFrame:
    require_columns(
        actual=places_context.columns,
        required=[
            "release_year",
            "year",
            "state_fips",
            "county_fips",
            "geography_name",
            "places_total_pop_18plus",
        ],
        context="PLACES context",
    )
    rows: list[pd.DataFrame] = []
    for condition_id, measure in PLACES_CONDITION_MEASURES.items():
        column = f"places_{measure.feature_prefix}_crude_prevalence"
        if column not in places_context.columns:
            continue
        subset = places_context.loc[
            places_context[column].notna(),
            [
                "release_year",
                "state_fips",
                "county_fips",
                "geography_name",
                "places_total_pop_18plus",
                column,
            ],
        ].copy()
        subset["condition_id"] = condition_id
        subset["places_measure_id"] = measure.measure_id
        year_column = f"places_{measure.feature_prefix}_estimate_year"
        subset["places_estimate_year"] = (
            pd.to_numeric(places_context[year_column], errors="coerce")
            if year_column in places_context.columns
            else pd.to_numeric(places_context["year"], errors="coerce")
        )
        subset["places_crude_prevalence"] = pd.to_numeric(subset[column], errors="coerce")
        rows.append(subset.drop(columns=[column]))
    if not rows:
        return pd.DataFrame()
    out = pd.concat(rows, ignore_index=True)
    out["state_fips"] = _clean_fips_series(out["state_fips"], 2)
    out["county_fips"] = _clean_fips_series(out["county_fips"], 5)
    return out


def _places_reference_for_level(places_rows: pd.DataFrame, *, level: str) -> pd.DataFrame:
    if places_rows.empty:
        return pd.DataFrame()
    group_columns = ["condition_id", "places_measure_id", "release_year", "places_estimate_year"]
    group_columns.extend(_geography_columns(level))
    rows: list[dict[str, Any]] = []
    for keys, group in places_rows.groupby(group_columns, dropna=False):
        key_values = keys if isinstance(keys, tuple) else (keys,)
        row: dict[str, Any] = {
            column: (None if pd.isna(value) else value)
            for column, value in zip(group_columns, key_values, strict=True)
        }
        if level == "county":
            row["geography_name"] = str(group["geography_name"].iloc[0])
            row["places_crude_prevalence"] = _weighted_mean(group["places_crude_prevalence"])
            row["places_reference_kind"] = "county_crude_prevalence"
        else:
            row["geography_name"] = (
                "United States"
                if level == "national"
                else str(group["geography_name"].iloc[0]).split(" County, ")[-1]
            )
            row["places_crude_prevalence"] = _weighted_mean(
                group["places_crude_prevalence"],
                group["places_total_pop_18plus"],
            )
            row["places_reference_kind"] = "population_weighted_crude_prevalence"
        row["geography_level"] = level
        rows.append(row)
    return pd.DataFrame(rows)


def _places_reference(places_context: pd.DataFrame, levels: Iterable[str]) -> pd.DataFrame:
    places_rows = _places_condition_rows(places_context)
    references = [_places_reference_for_level(places_rows, level=level) for level in set(levels)]
    references = [frame for frame in references if not frame.empty]
    return pd.concat(references, ignore_index=True) if references else pd.DataFrame()


def build_external_validation_report(
    *,
    model_aggregates: pd.DataFrame,
    places_context: pd.DataFrame,
) -> pd.DataFrame:
    """Build a reasonableness report comparing model aggregates with PLACES estimates."""
    model = normalize_model_aggregates(model_aggregates)
    if model.empty:
        return pd.DataFrame(columns=_REPORT_COLUMNS)
    places = _places_reference(places_context, model["geography_level"].unique().tolist())
    if places.empty:
        return pd.DataFrame(columns=_REPORT_COLUMNS)

    merge_columns = ["condition_id", "geography_level"]
    for column in ["state_fips", "county_fips"]:
        if column in model.columns and column in places.columns:
            merge_columns.append(column)
    report = model.merge(places, on=merge_columns, how="inner", validate="many_to_one")
    if report.empty:
        return pd.DataFrame(columns=_REPORT_COLUMNS)

    report["places_crude_prevalence_probability"] = report["places_crude_prevalence"] / 100.0
    report["absolute_difference"] = (
        report["model_mean_predicted_probability"] - report["places_crude_prevalence_probability"]
    )
    report["relative_difference"] = report["absolute_difference"] / report[
        "places_crude_prevalence_probability"
    ].where(report["places_crude_prevalence_probability"].ne(0))
    report["comparison_direction"] = report["absolute_difference"].map(_direction)
    report["places_is_model_based_context"] = True

    for column in _REPORT_COLUMNS:
        if column not in report.columns:
            report[column] = None
    return report.loc[:, _REPORT_COLUMNS].sort_values(
        ["condition_id", "geography_level", "state_fips", "county_fips"],
        na_position="first",
    )


def _load_bundle_model_aggregates(bundle_dir: Path) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    for condition_id in PLACES_CONDITION_MEASURES:
        prediction_path = bundle_dir / f"{condition_id}_predictions.parquet"
        if not prediction_path.exists():
            continue
        frame = pd.read_parquet(prediction_path)
        require_columns(
            actual=frame.columns,
            required=["predicted_probability"],
            context=f"{condition_id} predictions",
        )
        frame = frame.copy()
        frame["condition_id"] = condition_id
        rows.append(frame)
    if not rows:
        raise FileNotFoundError(f"No per-condition prediction parquet files found in {bundle_dir}.")
    return pd.concat(rows, ignore_index=True)


def _report_payload(report: pd.DataFrame, *, places_year: int) -> dict[str, Any]:
    rows = report.astype(object).where(pd.notna(report), None).to_dict(orient="records")
    return {
        "dataset_name": "places_external_context_validation",
        "generated_at": dt.datetime.now(dt.UTC).isoformat(),
        "places_release_year": places_year,
        "caveat": EXTERNAL_VALIDATION_CAVEAT,
        "summary": {
            "rows": len(rows),
            "conditions_compared": sorted({str(row["condition_id"]) for row in rows}),
        },
        "rows": rows,
    }


def _path_for_report(path: Path, *, root: Path) -> str:
    """Return a root-relative path when possible, else an absolute/local path string."""
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _collect_if_exists(files: list[FileProvenance], path: Path, *, root: Path) -> None:
    if path.exists():
        try:
            files.append(collect_file_provenance(path, root=root))
        except ValueError:
            files.append(collect_file_provenance(path))


def _places_source_registry_extra(places_year: int) -> dict[str, Any]:
    registry = load_data_source_registry()
    return {
        "source_registry_by_year": {
            str(places_year): registry_provenance_extra(
                registry=registry,
                source_ids=[PLACES_SOURCE_ID],
                year=places_year,
            )["source_registry"]
        }
    }


def _load_model_input(
    *,
    model_aggregate_path: Path | None,
    bundle_dir: Path | None,
) -> pd.DataFrame:
    if (model_aggregate_path is None) == (bundle_dir is None):
        raise ValueError("Provide exactly one of model_aggregate_path or bundle_dir.")
    if model_aggregate_path is not None:
        return _read_table(model_aggregate_path)
    if bundle_dir is None:  # pragma: no cover
        raise ValueError("bundle_dir is required when model_aggregate_path is not provided.")
    return _load_bundle_model_aggregates(bundle_dir)


def _filter_places_year(places_context: pd.DataFrame, *, places_year: int) -> pd.DataFrame:
    require_columns(
        actual=places_context.columns,
        required=["release_year"],
        context="PLACES context",
    )
    release_years = pd.to_numeric(places_context["release_year"], errors="coerce")
    filtered = places_context.loc[release_years == places_year].copy()
    if filtered.empty:
        raise ValueError(f"No PLACES context rows found for release_year={places_year}.")
    return filtered


def validate_external_context(
    *,
    base_dir: Path,
    places_year: int,
    model_aggregate_path: Path | None,
    bundle_dir: Path | None,
    force: bool,
    dry_run: bool,
) -> None:
    """Write an external reasonableness report against CDC PLACES county context."""
    json_path = places_external_validation_report_json_path(base_dir, places_year=places_year)
    csv_path = places_external_validation_report_csv_path(base_dir, places_year=places_year)
    if not force and json_path.exists() and csv_path.exists():
        print(f"Skip validation (exists): {json_path}")
        print(f"Skip validation (exists): {csv_path}")
        return

    places_path = places_county_year_parquet(base_dir)
    if not places_path.exists():
        raise FileNotFoundError(f"Missing PLACES context parquet: {places_path}.")
    places_context = _filter_places_year(pd.read_parquet(places_path), places_year=places_year)
    model_input = _load_model_input(
        model_aggregate_path=model_aggregate_path,
        bundle_dir=bundle_dir,
    )
    report = build_external_validation_report(
        model_aggregates=model_input,
        places_context=places_context,
    )

    if dry_run:
        print(f"DRY RUN: would write CSV report -> {csv_path}")
        print(f"DRY RUN: would write JSON report -> {json_path}")
    else:
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        report.to_csv(csv_path, index=False)
        json_path.write_text(
            json.dumps(_report_payload(report, places_year=places_year), indent=2) + "\n",
            encoding="utf-8",
        )

    files: list[FileProvenance] = []
    _collect_if_exists(files, places_path, root=base_dir)
    if model_aggregate_path is not None:
        _collect_if_exists(files, model_aggregate_path, root=base_dir)
    if bundle_dir is not None:
        for prediction_path in sorted(bundle_dir.glob("*_predictions.parquet")):
            _collect_if_exists(files, prediction_path, root=base_dir)
    _collect_if_exists(files, csv_path, root=base_dir)
    _collect_if_exists(files, json_path, root=base_dir)

    write_provenance_json(
        provenance_external_validation_path(base_dir, places_year=places_year),
        dataset_name="places_external_context_validation",
        dataset_version=str(places_year),
        sources=[places_county_csv_url(places_year)],
        files=files,
        extra={
            **_places_source_registry_extra(places_year),
            "places_release_year": places_year,
            "places_context_caveat": EXTERNAL_VALIDATION_CAVEAT,
            "report_outputs": [
                csv_path.relative_to(base_dir).as_posix(),
                json_path.relative_to(base_dir).as_posix(),
            ],
            "model_input": (
                _path_for_report(model_aggregate_path, root=base_dir)
                if model_aggregate_path is not None
                else str(bundle_dir)
            ),
            "comparison_rows": len(report),
        },
        dry_run=dry_run,
    )


def main(argv: list[str] | None = None) -> None:
    """CLI entrypoint for PLACES external reasonableness validation."""
    parser = argparse.ArgumentParser(
        description="Compare model aggregate risk patterns with CDC PLACES estimates."
    )
    add_common_pipeline_args(parser)
    model_group = parser.add_mutually_exclusive_group(required=True)
    model_group.add_argument(
        "--model-aggregate-path",
        type=Path,
        help="CSV, JSON, or Parquet table with condition_id and aggregate model probabilities.",
    )
    model_group.add_argument(
        "--bundle-dir",
        type=Path,
        help="Model bundle directory containing per-condition *_predictions.parquet files.",
    )
    args = parser.parse_args(argv)
    years = parse_years_from_args(args)
    if len(years) != 1:
        raise ValueError("External PLACES validation expects exactly one --year.")
    validate_external_context(
        base_dir=Path(args.base_dir),
        places_year=years[0],
        model_aggregate_path=args.model_aggregate_path,
        bundle_dir=args.bundle_dir,
        force=bool(args.force),
        dry_run=bool(args.dry_run),
    )


if __name__ == "__main__":
    main()
