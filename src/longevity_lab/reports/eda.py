"""Scripted EDA report generation from processed Longevity Lab tables."""

from __future__ import annotations

import argparse
import html
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import pandas as pd  # type: ignore[import-untyped]

from longevity_lab.domain.catalog import CONDITIONS
from longevity_lab.pipeline.common import default_data_dir, parse_years_csv, require_columns
from longevity_lab.reports.figures import BarDatum, write_bar_chart_png, write_bar_chart_svg

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG_PATH = REPO_ROOT / "conf" / "reports" / "eda.yaml"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "reports" / "eda"
REPRODUCIBLE_GENERATED_AT = "not-recorded-for-reproducibility"

DEFAULT_NUMERIC_FEATURES: tuple[str, ...] = (
    "age",
    "bmi",
    "alcohol_servings_per_week",
    "exercise_minutes_per_week",
    "annual_aqi",
    "pm25_mean",
    "ozone_mean",
    "physical_health_days",
    "mental_health_days",
    "sleep_hours_per_night",
    "survey_weight",
)
DEFAULT_CATEGORICAL_FEATURES: tuple[str, ...] = (
    "sex",
    "race_ethnicity",
    "smoker",
    "has_healthcare_coverage",
    "has_personal_doctor",
    "cost_barrier_to_care",
    "last_checkup_within_year",
)
DEFAULT_LABEL_COLUMNS: dict[str, str] = {
    condition.condition_id: f"label_{condition.condition_id}" for condition in CONDITIONS
}
CONDITION_LABELS: dict[str, str] = {
    condition.condition_id: condition.label for condition in CONDITIONS
}


@dataclass(frozen=True, slots=True)
class EdaReportConfig:
    """Configuration for one scripted EDA report run."""

    schema_version: int
    report_id: str
    title: str
    base_dir: Path
    years: tuple[int, ...]
    output_dir: Path
    integrated_path_template: str
    numeric_features: tuple[str, ...]
    categorical_features: tuple[str, ...]
    label_columns: Mapping[str, str]
    optional_table_paths: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class EdaReportResult:
    """Paths written by a scripted EDA report run."""

    summary_json: Path
    markdown_report: Path
    html_report: Path
    figure_paths: Mapping[str, Path]


def _mapping(value: object, *, context: str) -> dict[str, object]:
    """Return a JSON mapping or raise a configuration error."""
    if not isinstance(value, dict):
        raise ValueError(f"Expected {context} to be a mapping.")
    return cast(dict[str, object], value)


def _string_tuple(value: object, *, default: Sequence[str], context: str) -> tuple[str, ...]:
    """Return a tuple of strings from a config sequence."""
    if value is None:
        return tuple(default)
    if not isinstance(value, list):
        raise ValueError(f"Expected {context} to be a list.")
    return tuple(str(item) for item in value)


def _config_int(value: object, *, context: str) -> int:
    """Return an integer from a JSON scalar config value."""
    try:
        return int(cast(Any, value))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Expected {context} to be an integer.") from exc


def _path_from_config(value: object, *, root_dir: Path, default: Path) -> Path:
    """Resolve a config path relative to the repository root."""
    if value is None:
        return default
    path = Path(str(value))
    if path.is_absolute():
        return path
    return root_dir / path


def default_config_path() -> Path:
    """Return the repo-local EDA report config path."""
    return DEFAULT_CONFIG_PATH


def load_eda_config(path: Path | None = None) -> EdaReportConfig:
    """Load the JSON-compatible YAML report configuration."""
    config_path = path or DEFAULT_CONFIG_PATH
    payload = _mapping(json.loads(config_path.read_text(encoding="utf-8")), context="EDA config")
    root_dir = _path_from_config(payload.get("root_dir"), root_dir=REPO_ROOT, default=REPO_ROOT)
    data = _mapping(payload.get("data", {}), context="EDA config data")
    features = _mapping(payload.get("features", {}), context="EDA config features")
    labels_payload = features.get("labels", DEFAULT_LABEL_COLUMNS)
    labels = _mapping(labels_payload, context="EDA labels")
    optional_tables = _mapping(data.get("optional_tables", {}), context="EDA optional tables")

    years_raw = data.get("years", [])
    if not isinstance(years_raw, list):
        raise ValueError("Expected EDA data.years to be a list.")
    years = tuple(sorted(_config_int(year, context="EDA data.years item") for year in years_raw))
    if not years:
        raise ValueError("EDA report config must include at least one year.")

    return EdaReportConfig(
        schema_version=_config_int(payload.get("schema_version", 1), context="schema_version"),
        report_id=str(payload.get("report_id", "eda")),
        title=str(payload.get("title", "Longevity Lab scripted EDA")),
        base_dir=_path_from_config(
            data.get("base_dir"),
            root_dir=root_dir,
            default=default_data_dir(),
        ),
        years=years,
        output_dir=_path_from_config(
            payload.get("output_dir"),
            root_dir=root_dir,
            default=DEFAULT_OUTPUT_DIR,
        ),
        integrated_path_template=str(
            data.get(
                "integrated_path_template",
                "processed/integrated/{year}/integrated_person_year.parquet",
            )
        ),
        numeric_features=_string_tuple(
            features.get("numeric"),
            default=DEFAULT_NUMERIC_FEATURES,
            context="EDA numeric features",
        ),
        categorical_features=_string_tuple(
            features.get("categorical"),
            default=DEFAULT_CATEGORICAL_FEATURES,
            context="EDA categorical features",
        ),
        label_columns={str(key): str(value) for key, value in labels.items()},
        optional_table_paths={str(key): str(value) for key, value in optional_tables.items()},
    )


def _with_overrides(
    config: EdaReportConfig,
    *,
    base_dir: Path | None,
    years: Sequence[int] | None,
    output_dir: Path | None,
) -> EdaReportConfig:
    """Return a config with CLI overrides applied."""
    return EdaReportConfig(
        schema_version=config.schema_version,
        report_id=config.report_id,
        title=config.title,
        base_dir=base_dir or config.base_dir,
        years=tuple(sorted({int(year) for year in years})) if years is not None else config.years,
        output_dir=output_dir or config.output_dir,
        integrated_path_template=config.integrated_path_template,
        numeric_features=config.numeric_features,
        categorical_features=config.categorical_features,
        label_columns=config.label_columns,
        optional_table_paths=config.optional_table_paths,
    )


def _template_path(base_dir: Path, template: str, *, year: int | None = None) -> Path:
    """Resolve a configured processed-table path template."""
    formatted = template.format(year=year) if year is not None else template
    path = Path(formatted)
    if path.is_absolute():
        return path
    return base_dir / path


def _read_integrated_person_year(config: EdaReportConfig) -> tuple[pd.DataFrame, list[Path]]:
    """Read and concatenate requested integrated person-year parquet files."""
    paths = [
        _template_path(config.base_dir, config.integrated_path_template, year=year)
        for year in config.years
    ]
    missing = [path for path in paths if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Missing processed integrated table: {missing[0]}")

    frames = [pd.read_parquet(path) for path in paths]
    frame = pd.concat(frames, ignore_index=True)
    require_columns(
        actual=frame.columns,
        required=["year", "state_fips", *config.label_columns.values()],
        context="EDA integrated_person_year",
    )
    return frame, paths


def _round_or_none(value: object, *, digits: int = 6) -> float | None:
    """Return a rounded float unless the value is missing."""
    if pd.isna(value):
        return None
    return round(float(cast(Any, value)), digits)


def _numeric_summary(frame: pd.DataFrame, columns: Sequence[str]) -> dict[str, dict[str, Any]]:
    """Summarize configured numeric columns that exist in the input frame."""
    summary: dict[str, dict[str, Any]] = {}
    row_count = max(1, len(frame))
    for column in columns:
        if column not in frame.columns:
            continue
        series = pd.to_numeric(frame[column], errors="coerce")
        values = series.dropna()
        summary[column] = {
            "count": int(values.count()),
            "missing_count": int(series.isna().sum()),
            "missing_rate": float(series.isna().sum() / row_count),
            "mean": _round_or_none(values.mean()),
            "median": _round_or_none(values.median()),
            "min": _round_or_none(values.min()),
            "max": _round_or_none(values.max()),
        }
    return summary


def _categorical_summary(frame: pd.DataFrame, columns: Sequence[str]) -> dict[str, dict[str, Any]]:
    """Summarize configured categorical columns that exist in the input frame."""
    summary: dict[str, dict[str, Any]] = {}
    row_count = max(1, len(frame))
    for column in columns:
        if column not in frame.columns:
            continue
        series = frame[column].map(lambda value: "missing" if pd.isna(value) else str(value))
        counts = series.value_counts(dropna=False).sort_index()
        missing_count = int((series == "missing").sum())
        summary[column] = {
            "count": int(len(series)),
            "missing_count": missing_count,
            "missing_rate": float(missing_count / row_count),
            "distinct_count": int(counts.size),
            "counts": {str(index): int(value) for index, value in counts.items()},
        }
    return summary


def _label_prevalence(
    frame: pd.DataFrame,
    labels: Mapping[str, str],
) -> dict[str, dict[str, Any]]:
    """Summarize binary label prevalence by condition."""
    summary: dict[str, dict[str, Any]] = {}
    weights = (
        pd.to_numeric(frame["survey_weight"], errors="coerce") if "survey_weight" in frame else None
    )
    for condition_id, column in labels.items():
        series = pd.to_numeric(frame[column], errors="coerce")
        valid = series.dropna()
        positive = valid == 1
        condition_summary: dict[str, Any] = {
            "label": CONDITION_LABELS.get(condition_id, condition_id.replace("_", " ").title()),
            "column": column,
            "rows": int(valid.count()),
            "positive_rows": int(positive.sum()),
            "negative_rows": int((valid == 0).sum()),
            "missing_rows": int(series.isna().sum()),
            "positive_rate": float(positive.mean()) if len(valid) else None,
        }
        if weights is not None:
            valid_weights = weights.loc[valid.index].fillna(0.0)
            denominator = float(valid_weights.sum())
            numerator = float(valid_weights.loc[positive.index[positive]].sum())
            condition_summary["weighted_positive_rate"] = (
                numerator / denominator if denominator > 0 else None
            )
        summary[condition_id] = condition_summary
    return summary


def _optional_table_summaries(config: EdaReportConfig) -> dict[str, dict[str, Any]]:
    """Summarize configured optional processed tables when present."""
    summaries: dict[str, dict[str, Any]] = {}
    for table_name, template in config.optional_table_paths.items():
        path = _template_path(config.base_dir, template)
        display_path = _display_path(path, root=config.base_dir)
        if not path.exists():
            summaries[table_name] = {"status": "missing", "path": display_path}
            continue
        frame = pd.read_parquet(path)
        years: list[int] = []
        if "year" in frame.columns:
            year_values = pd.to_numeric(frame["year"], errors="coerce").dropna().unique()
            years = sorted(int(year) for year in year_values)
        summaries[table_name] = {
            "status": "present",
            "path": display_path,
            "row_count": int(len(frame)),
            "column_count": int(len(frame.columns)),
            "columns": [str(column) for column in frame.columns],
            "years": years,
        }
    return summaries


def _missingness_bars(
    numeric: Mapping[str, Mapping[str, Any]],
    categorical: Mapping[str, Mapping[str, Any]],
) -> list[BarDatum]:
    """Return bar data for configured feature missingness."""
    rows: list[BarDatum] = []
    for column, stats in {**numeric, **categorical}.items():
        rows.append(BarDatum(label=column, value=float(stats["missing_rate"]) * 100.0))
    return sorted(rows, key=lambda item: (-item.value, item.label))[:12]


def _prevalence_bars(prevalence: Mapping[str, Mapping[str, Any]]) -> list[BarDatum]:
    """Return bar data for condition prevalence."""
    rows: list[BarDatum] = []
    for condition_id, stats in prevalence.items():
        positive_rate = stats.get("positive_rate")
        value = 0.0 if positive_rate is None else float(positive_rate) * 100.0
        rows.append(BarDatum(label=str(stats.get("label", condition_id)), value=value))
    return rows


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    """Write an indented JSON document."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _display_path(path: Path, *, root: Path) -> str:
    """Return stable root-relative path text when possible."""
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _markdown_table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    """Return a GitHub-Flavored Markdown table."""
    header = "| " + " | ".join(headers) + " |"
    separator = "| " + " | ".join("---" for _ in headers) + " |"
    body = ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join([header, separator, *body])


def _write_markdown(
    path: Path,
    *,
    config: EdaReportConfig,
    summary: Mapping[str, Any],
) -> None:
    """Write the Markdown EDA report."""
    label_prevalence = cast(Mapping[str, Mapping[str, Any]], summary["label_prevalence"])
    prevalence_rows = [
        [
            str(stats["label"]),
            str(stats["column"]),
            str(stats["rows"]),
            str(stats["positive_rows"]),
            (
                f"{float(stats['positive_rate']) * 100:.1f}%"
                if stats["positive_rate"] is not None
                else "n/a"
            ),
        ]
        for stats in label_prevalence.values()
    ]
    numeric_features = cast(Mapping[str, Mapping[str, Any]], summary["numeric_features"])
    numeric_rows = [
        [
            column,
            str(stats["count"]),
            f"{float(stats['missing_rate']) * 100:.1f}%",
            "n/a" if stats["mean"] is None else f"{float(stats['mean']):.2f}",
            "n/a" if stats["median"] is None else f"{float(stats['median']):.2f}",
        ]
        for column, stats in numeric_features.items()
    ]
    lines = [
        f"# {config.title}",
        "",
        f"- Report ID: `{config.report_id}`",
        f"- Generated at: `{summary['generated_at']}`",
        f"- Years: `{', '.join(str(year) for year in config.years)}`",
        f"- Integrated rows: `{summary['input_tables']['integrated_person_year']['row_count']}`",
        "",
        "## Notebook status",
        "",
        "Notebooks are optional exploration artifacts. Canonical analysis evidence comes from "
        "this scripted report command and its machine-readable outputs.",
        "",
        "## Figures",
        "",
        "![Condition prevalence](figures/condition_prevalence.svg)",
        "",
        "![Feature missingness](figures/feature_missingness.svg)",
        "",
        "## Label Prevalence",
        "",
        _markdown_table(
            ["Condition", "Column", "Rows", "Positive rows", "Positive rate"],
            prevalence_rows,
        ),
        "",
        "## Numeric Features",
        "",
        _markdown_table(["Feature", "Count", "Missing", "Mean", "Median"], numeric_rows),
        "",
        "## Outputs",
        "",
        "- `summaries/eda_summary.json`",
        "- `figures/condition_prevalence.svg` and `figures/condition_prevalence.png`",
        "- `figures/feature_missingness.svg` and `figures/feature_missingness.png`",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_html(
    path: Path,
    *,
    config: EdaReportConfig,
    summary: Mapping[str, Any],
) -> None:
    """Write a simple static HTML EDA report."""
    markdown_report = config.output_dir / "eda_report.md"
    markdown_text = markdown_report.read_text(encoding="utf-8") if markdown_report.exists() else ""
    body = html.escape(markdown_text)
    html_text = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{html.escape(config.title)}</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 2rem; line-height: 1.5; color: #111827; }}
    img {{ max-width: 100%; border: 1px solid #e5e7eb; }}
    pre {{ white-space: pre-wrap; background: #f9fafb; padding: 1rem; }}
  </style>
</head>
<body>
  <h1>{html.escape(config.title)}</h1>
  <p><strong>Report ID:</strong> {html.escape(config.report_id)}</p>
  <p><strong>Generated at:</strong> {html.escape(str(summary["generated_at"]))}</p>
  <h2>Figures</h2>
  <img src="figures/condition_prevalence.svg" alt="Condition prevalence bar chart">
  <img src="figures/feature_missingness.svg" alt="Feature missingness bar chart">
  <h2>Markdown Source</h2>
  <pre>{body}</pre>
</body>
</html>
"""
    path.write_text(html_text, encoding="utf-8")


def run_eda_report(
    *,
    config_path: Path | None = None,
    base_dir: Path | None = None,
    years: Sequence[int] | None = None,
    output_dir: Path | None = None,
    dry_run: bool = False,
) -> EdaReportResult:
    """Generate scripted EDA summaries, figures, and report documents."""
    loaded_config = load_eda_config(config_path)
    config = _with_overrides(
        loaded_config,
        base_dir=base_dir,
        years=years,
        output_dir=output_dir,
    )
    integrated, integrated_paths = _read_integrated_person_year(config)
    numeric = _numeric_summary(integrated, config.numeric_features)
    categorical = _categorical_summary(integrated, config.categorical_features)
    labels = _label_prevalence(integrated, config.label_columns)
    summary: dict[str, Any] = {
        "schema_version": config.schema_version,
        "report_id": config.report_id,
        "title": config.title,
        "generated_at": REPRODUCIBLE_GENERATED_AT,
        "input_tables": {
            "integrated_person_year": {
                "paths": [_display_path(path, root=config.base_dir) for path in integrated_paths],
                "row_count": int(len(integrated)),
                "column_count": int(len(integrated.columns)),
                "columns": [str(column) for column in integrated.columns],
                "years": list(config.years),
            },
            **_optional_table_summaries(config),
        },
        "configured_features": {
            "numeric": list(config.numeric_features),
            "categorical": list(config.categorical_features),
            "labels": dict(config.label_columns),
        },
        "numeric_features": numeric,
        "categorical_features": categorical,
        "label_prevalence": labels,
        "notebook_policy": (
            "Notebooks are optional exploration artifacts; scripted report outputs are "
            "canonical evidence."
        ),
    }

    summary_json = config.output_dir / "summaries" / "eda_summary.json"
    markdown_report = config.output_dir / "eda_report.md"
    html_report = config.output_dir / "eda_report.html"
    figures_dir = config.output_dir / "figures"
    figure_paths = {
        "condition_prevalence_svg": figures_dir / "condition_prevalence.svg",
        "condition_prevalence_png": figures_dir / "condition_prevalence.png",
        "feature_missingness_svg": figures_dir / "feature_missingness.svg",
        "feature_missingness_png": figures_dir / "feature_missingness.png",
    }

    if dry_run:
        print(f"DRY RUN: would write report outputs under {config.output_dir}")
        return EdaReportResult(
            summary_json=summary_json,
            markdown_report=markdown_report,
            html_report=html_report,
            figure_paths=figure_paths,
        )

    _write_json(summary_json, summary)
    prevalence_bars = _prevalence_bars(labels)
    missingness_bars = _missingness_bars(numeric, categorical)
    write_bar_chart_svg(
        figure_paths["condition_prevalence_svg"],
        prevalence_bars,
        title="Condition label prevalence",
        y_axis_label="Positive rate",
        value_suffix="%",
    )
    write_bar_chart_png(figure_paths["condition_prevalence_png"], prevalence_bars)
    write_bar_chart_svg(
        figure_paths["feature_missingness_svg"],
        missingness_bars,
        title="Feature missingness",
        y_axis_label="Missing rows",
        value_suffix="%",
    )
    write_bar_chart_png(figure_paths["feature_missingness_png"], missingness_bars)
    _write_markdown(markdown_report, config=config, summary=summary)
    _write_html(html_report, config=config, summary=summary)

    print(f"Wrote EDA summary: {summary_json}")
    print(f"Wrote EDA report: {markdown_report}")
    return EdaReportResult(
        summary_json=summary_json,
        markdown_report=markdown_report,
        html_report=html_report,
        figure_paths=figure_paths,
    )


def main(argv: list[str] | None = None) -> None:
    """CLI entrypoint for scripted EDA report generation."""
    parser = argparse.ArgumentParser(
        description="Generate scripted EDA reports from processed Longevity Lab tables."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help=f"Report config path (default: {DEFAULT_CONFIG_PATH}).",
    )
    parser.add_argument(
        "--base-dir",
        type=Path,
        default=None,
        help="Override processed data base directory from the config.",
    )
    parser.add_argument("--year", type=int, help="Single year to report.")
    parser.add_argument("--years", type=str, help="Comma-separated years to report.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Override report output directory from the config.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Read inputs and print output paths without writing report files.",
    )
    args = parser.parse_args(argv)

    years: list[int] | None = None
    if args.year is not None and args.years is not None:
        parser.error("Use either --year or --years, not both.")
    if args.year is not None:
        years = [int(args.year)]
    elif args.years is not None:
        years = parse_years_csv(str(args.years))

    run_eda_report(
        config_path=Path(args.config),
        base_dir=Path(args.base_dir) if args.base_dir is not None else None,
        years=years,
        output_dir=Path(args.output_dir) if args.output_dir is not None else None,
        dry_run=bool(args.dry_run),
    )


if __name__ == "__main__":
    main()
