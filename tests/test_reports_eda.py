"""Tests for scripted EDA report generation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd  # type: ignore[import-untyped]
import pytest

from longevity_lab.reports.eda import run_eda_report


def _write_processed_integrated_table(path: Path) -> None:
    """Write a tiny processed person-year table for report tests."""
    frame = pd.DataFrame(
        [
            {
                "year": 2023,
                "state_fips": "01",
                "sex": "female",
                "race_ethnicity": "white_non_hispanic",
                "age": 42,
                "bmi": 24.0,
                "smoker": False,
                "alcohol_servings_per_week": 1,
                "exercise_minutes_per_week": 180,
                "annual_aqi": 45,
                "pm25_mean": 7.5,
                "ozone_mean": 0.041,
                "label_heart_disease": 0,
                "label_chronic_lung_disease": 0,
                "label_stroke": 0,
                "label_depression": 0,
                "label_diabetes": 0,
                "survey_weight": 1.0,
            },
            {
                "year": 2023,
                "state_fips": "01",
                "sex": "male",
                "race_ethnicity": "black_non_hispanic",
                "age": 68,
                "bmi": 31.5,
                "smoker": True,
                "alcohol_servings_per_week": 8,
                "exercise_minutes_per_week": 60,
                "annual_aqi": 55,
                "pm25_mean": 8.0,
                "ozone_mean": 0.044,
                "label_heart_disease": 1,
                "label_chronic_lung_disease": 1,
                "label_stroke": 0,
                "label_depression": 1,
                "label_diabetes": 1,
                "survey_weight": 2.0,
            },
            {
                "year": 2023,
                "state_fips": "06",
                "sex": "female",
                "race_ethnicity": "hispanic",
                "age": 57,
                "bmi": 29.0,
                "smoker": False,
                "alcohol_servings_per_week": 3,
                "exercise_minutes_per_week": 120,
                "annual_aqi": 70,
                "pm25_mean": None,
                "ozone_mean": 0.052,
                "label_heart_disease": 0,
                "label_chronic_lung_disease": 0,
                "label_stroke": 1,
                "label_depression": 0,
                "label_diabetes": 0,
                "survey_weight": 1.5,
            },
            {
                "year": 2023,
                "state_fips": "06",
                "sex": None,
                "race_ethnicity": "hispanic",
                "age": 73,
                "bmi": None,
                "smoker": True,
                "alcohol_servings_per_week": 14,
                "exercise_minutes_per_week": 20,
                "annual_aqi": 80,
                "pm25_mean": 9.1,
                "ozone_mean": None,
                "label_heart_disease": 1,
                "label_chronic_lung_disease": 1,
                "label_stroke": 1,
                "label_depression": 1,
                "label_diabetes": 1,
                "survey_weight": 0.5,
            },
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False)


def _write_report_config(
    path: Path,
    *,
    base_dir: Path,
    output_dir: Path,
    include_optional_tables: bool = False,
) -> None:
    """Write JSON-compatible YAML report config for tests."""
    payload: dict[str, Any] = {
        "schema_version": 1,
        "report_id": "test_eda",
        "title": "Test scripted EDA",
        "output_dir": str(output_dir),
        "data": {
            "base_dir": str(base_dir),
            "years": [2023],
            "integrated_path_template": (
                "processed/integrated/{year}/integrated_person_year.parquet"
            ),
        },
        "features": {
            "numeric": ["age", "bmi", "annual_aqi", "pm25_mean", "ozone_mean"],
            "categorical": ["sex", "race_ethnicity", "smoker"],
            "labels": {
                "heart_disease": "label_heart_disease",
                "chronic_lung_disease": "label_chronic_lung_disease",
                "stroke": "label_stroke",
                "depression": "label_depression",
                "diabetes": "label_diabetes",
            },
        },
    }
    if include_optional_tables:
        payload["data"]["optional_tables"] = {
            "context_state_year": "processed/context/context_state_year.parquet",
            "missing_context_county_year": "processed/context/context_county_year.parquet",
        }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_run_eda_report_writes_canonical_outputs_from_processed_data(tmp_path: Path) -> None:
    """The report command should write summaries, figures, and report documents."""
    base_dir = tmp_path / "data"
    output_dir = tmp_path / "reports" / "eda"
    config_path = tmp_path / "conf" / "reports" / "eda.yaml"
    _write_processed_integrated_table(
        base_dir / "processed" / "integrated" / "2023" / "integrated_person_year.parquet"
    )
    _write_report_config(config_path, base_dir=base_dir, output_dir=output_dir)

    result = run_eda_report(config_path=config_path)

    assert result.summary_json == output_dir / "summaries" / "eda_summary.json"
    assert result.markdown_report == output_dir / "eda_report.md"
    assert result.html_report == output_dir / "eda_report.html"
    assert result.summary_json.exists()
    assert result.markdown_report.exists()
    assert result.html_report.exists()
    assert result.figure_paths["condition_prevalence_svg"].exists()
    assert result.figure_paths["condition_prevalence_png"].exists()
    assert result.figure_paths["feature_missingness_svg"].exists()
    assert result.figure_paths["feature_missingness_png"].exists()
    assert result.figure_paths["condition_prevalence_png"].read_bytes().startswith(b"\x89PNG")

    summary = json.loads(result.summary_json.read_text(encoding="utf-8"))
    assert summary["schema_version"] == 1
    assert summary["report_id"] == "test_eda"
    assert summary["input_tables"]["integrated_person_year"]["row_count"] == 4
    assert summary["input_tables"]["integrated_person_year"]["paths"] == [
        "processed/integrated/2023/integrated_person_year.parquet"
    ]
    assert summary["label_prevalence"]["heart_disease"]["positive_rate"] == pytest.approx(0.5)
    assert summary["numeric_features"]["bmi"]["missing_rate"] == pytest.approx(0.25)
    assert summary["categorical_features"]["smoker"]["counts"] == {"False": 2, "True": 2}

    markdown = result.markdown_report.read_text(encoding="utf-8")
    assert "Notebook status" in markdown
    assert "optional exploration artifacts" in markdown
    assert "condition_prevalence.svg" in markdown


def test_run_eda_report_is_reproducible_for_identical_inputs(tmp_path: Path) -> None:
    """Repeat report runs on unchanged inputs should produce stable canonical files."""
    base_dir = tmp_path / "data"
    output_dir = tmp_path / "reports" / "eda"
    config_path = tmp_path / "conf" / "reports" / "eda.yaml"
    _write_processed_integrated_table(
        base_dir / "processed" / "integrated" / "2023" / "integrated_person_year.parquet"
    )
    _write_report_config(config_path, base_dir=base_dir, output_dir=output_dir)

    first = run_eda_report(config_path=config_path)
    first_bytes = {
        "json": first.summary_json.read_bytes(),
        "markdown": first.markdown_report.read_bytes(),
        "html": first.html_report.read_bytes(),
        "prevalence_svg": first.figure_paths["condition_prevalence_svg"].read_bytes(),
        "missingness_svg": first.figure_paths["feature_missingness_svg"].read_bytes(),
    }

    second = run_eda_report(config_path=config_path)
    second_bytes = {
        "json": second.summary_json.read_bytes(),
        "markdown": second.markdown_report.read_bytes(),
        "html": second.html_report.read_bytes(),
        "prevalence_svg": second.figure_paths["condition_prevalence_svg"].read_bytes(),
        "missingness_svg": second.figure_paths["feature_missingness_svg"].read_bytes(),
    }

    assert first_bytes == second_bytes


def test_run_eda_report_summary_paths_are_location_reproducible(tmp_path: Path) -> None:
    """Summary metadata should not encode clone-specific absolute data roots."""
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    for root in [first_root, second_root]:
        base_dir = root / "data"
        output_dir = root / "reports" / "eda"
        config_path = root / "conf" / "reports" / "eda.yaml"
        _write_processed_integrated_table(
            base_dir / "processed" / "integrated" / "2023" / "integrated_person_year.parquet"
        )
        optional_path = base_dir / "processed" / "context" / "context_state_year.parquet"
        optional_path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame([{"year": 2023, "state_fips": "01", "acs_poverty_percent": 12.5}]).to_parquet(
            optional_path, index=False
        )
        _write_report_config(
            config_path,
            base_dir=base_dir,
            output_dir=output_dir,
            include_optional_tables=True,
        )
        run_eda_report(config_path=config_path)

    first_summary = json.loads(
        (first_root / "reports" / "eda" / "summaries" / "eda_summary.json").read_text(
            encoding="utf-8"
        )
    )
    second_summary = json.loads(
        (second_root / "reports" / "eda" / "summaries" / "eda_summary.json").read_text(
            encoding="utf-8"
        )
    )

    assert first_summary == second_summary
    assert first_summary["input_tables"]["context_state_year"]["path"] == (
        "processed/context/context_state_year.parquet"
    )
    assert first_summary["input_tables"]["missing_context_county_year"]["path"] == (
        "processed/context/context_county_year.parquet"
    )


def test_run_eda_report_requires_processed_integrated_table(tmp_path: Path) -> None:
    """Missing processed inputs should fail before writing canonical reports."""
    base_dir = tmp_path / "data"
    output_dir = tmp_path / "reports" / "eda"
    config_path = tmp_path / "conf" / "reports" / "eda.yaml"
    _write_report_config(config_path, base_dir=base_dir, output_dir=output_dir)

    with pytest.raises(FileNotFoundError, match="Missing processed integrated table"):
        run_eda_report(config_path=config_path)

    assert not output_dir.exists()
