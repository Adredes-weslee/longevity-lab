"""Dataset preparation for non-serving causal workbench analyses."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd  # type: ignore[import-untyped]
import yaml  # type: ignore[import-untyped]

from longevity_lab.pipeline.ingest import build_ingest_paths

REPO_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True, slots=True)
class CausalWorkbenchConfig:
    """Configuration for one scripted causal analysis."""

    schema_version: int
    question_id: str
    title: str
    source_question_registry: Path
    treatment_name: str
    treatment_contrast: str
    treatment_column: str
    outcome_name: str
    outcome_timing: str
    outcome_column: str
    sample_weight_column: str
    required_columns: tuple[str, ...]
    adjustment_columns: tuple[str, ...]
    categorical_columns: tuple[str, ...]
    excluded_columns: tuple[str, ...]
    negative_control_outcomes: tuple[str, ...]
    negative_control_exposures: tuple[str, ...]
    sensitivity_checks: tuple[str, ...]
    dag_version: str
    dag_edges: tuple[str, ...]
    residual_risks: tuple[str, ...]
    estimand: dict[str, Any]
    assumptions: tuple[str, ...]
    random_state: int
    min_propensity: float
    max_propensity: float
    trim_min_propensity: float
    trim_max_propensity: float
    max_abs_smd_warning: float
    data_year: int
    base_dir: Path
    input_path: Path | None
    sample_path: Path | None
    use_sample_if_missing: bool
    output_dir: Path
    json_name: str
    markdown_name: str


@dataclass(frozen=True, slots=True)
class PreparedCausalDataset:
    """Analysis-ready table and preparation diagnostics for a causal question."""

    question_id: str
    frame: pd.DataFrame
    source_path: Path
    input_rows: int
    analysis_rows: int
    exclusions: dict[str, int]
    missingness: dict[str, int]
    weight_imputation: dict[str, float | int]


def default_smoking_lung_config_path() -> Path:
    """Return the repo-local smoking-to-lung-disease workbench config path."""
    return REPO_ROOT / "conf" / "causal" / "smoking_lung.yaml"


def load_smoking_lung_config(path: Path | None = None) -> CausalWorkbenchConfig:
    """Load the JSON-compatible config for the PR12 smoking causal prototype."""
    config_path = resolve_repo_path(path) if path else default_smoking_lung_config_path()
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    return _config_from_payload(payload)


def resolve_repo_path(path: Path) -> Path:
    """Resolve repo-local config paths independent of the caller's current directory."""
    return path if path.is_absolute() else REPO_ROOT / path


def prepare_smoking_lung_dataset(
    *,
    input_path: Path | None = None,
    config: CausalWorkbenchConfig | None = None,
) -> PreparedCausalDataset:
    """Prepare the smoking-to-lung-disease analysis dataset from processed person rows."""
    causal_config = config or load_smoking_lung_config()
    source_path = _resolve_input_path(input_path=input_path, config=causal_config)
    frame = _read_person_year_table(source_path)
    _require_columns(frame, causal_config.required_columns)

    input_rows = len(frame)
    working = frame.copy()
    working[causal_config.treatment_column] = _coerce_binary(
        working[causal_config.treatment_column]
    )
    working[causal_config.outcome_column] = _coerce_binary(working[causal_config.outcome_column])

    exclusions: dict[str, int] = {}
    missing_treatment = working[causal_config.treatment_column].isna()
    exclusions["missing_treatment"] = int(missing_treatment.sum())
    working = working.loc[~missing_treatment].copy()

    missing_outcome = working[causal_config.outcome_column].isna()
    exclusions["missing_outcome"] = int(missing_outcome.sum())
    working = working.loc[~missing_outcome].copy()

    age = pd.to_numeric(working["age"], errors="coerce")
    outside_adult_age = age.isna() | (age < 18) | (age > 100)
    exclusions["outside_adult_age_range"] = int(outside_adult_age.sum())
    working = working.loc[~outside_adult_age].copy()

    analysis_columns = _analysis_columns(causal_config)
    working = working.loc[:, analysis_columns].reset_index(drop=True)
    working[causal_config.treatment_column] = working[causal_config.treatment_column].astype(int)
    working[causal_config.outcome_column] = working[causal_config.outcome_column].astype(int)

    missingness = {
        column: int(working[column].isna().sum())
        for column in causal_config.adjustment_columns
        if column in working.columns
    }
    weight_imputation = _coerce_sample_weights(working, causal_config.sample_weight_column)

    return PreparedCausalDataset(
        question_id=causal_config.question_id,
        frame=working,
        source_path=source_path,
        input_rows=input_rows,
        analysis_rows=len(working),
        exclusions={key: value for key, value in exclusions.items() if value},
        missingness=missingness,
        weight_imputation=weight_imputation,
    )


def _config_from_payload(payload: dict[str, Any]) -> CausalWorkbenchConfig:
    columns = payload["columns"]
    diagnostics = payload["diagnostics"]
    data = payload["data"]
    reports = payload["reports"]
    estimator = payload["estimator"]
    registry_path = resolve_repo_path(Path(str(payload["source_question_registry"])))
    registry_question = _load_registry_question(registry_path, str(payload["question_id"]))
    dag = registry_question["dag_assumptions"]
    return CausalWorkbenchConfig(
        schema_version=int(payload["schema_version"]),
        question_id=str(payload["question_id"]),
        title=str(registry_question["title"]),
        source_question_registry=registry_path,
        treatment_name=str(registry_question["treatment"]["name"]),
        treatment_contrast=str(registry_question["treatment"]["contrast"]),
        treatment_column=str(columns["treatment"]),
        outcome_name=str(registry_question["outcome"]["name"]),
        outcome_timing=str(registry_question["outcome"]["timing"]),
        outcome_column=str(columns["outcome"]),
        sample_weight_column=str(columns["sample_weight"]),
        required_columns=_tuple(columns["required"]),
        adjustment_columns=_tuple(columns["adjustment"]),
        categorical_columns=_tuple(columns.get("categorical", [])),
        excluded_columns=_tuple(columns["excluded"]),
        negative_control_outcomes=_tuple(registry_question["negative_controls"]["outcomes"]),
        negative_control_exposures=_tuple(registry_question["negative_controls"]["exposures"]),
        sensitivity_checks=_tuple(registry_question["sensitivity_checks"]),
        dag_version=str(dag["version"]),
        dag_edges=_tuple(dag["key_edges"]),
        residual_risks=_tuple(dag["residual_risks"]),
        estimand=dict(registry_question["estimand"]),
        assumptions=_tuple(payload["assumptions"]),
        random_state=int(estimator["random_state"]),
        min_propensity=float(diagnostics["min_propensity"]),
        max_propensity=float(diagnostics["max_propensity"]),
        trim_min_propensity=float(diagnostics["trim_min_propensity"]),
        trim_max_propensity=float(diagnostics["trim_max_propensity"]),
        max_abs_smd_warning=float(diagnostics["max_abs_smd_warning"]),
        data_year=int(data["year"]),
        base_dir=resolve_repo_path(Path(str(data["base_dir"]))),
        input_path=(
            resolve_repo_path(Path(str(data["input_path"]))) if data.get("input_path") else None
        ),
        sample_path=(
            resolve_repo_path(Path(str(data["sample_path"]))) if data.get("sample_path") else None
        ),
        use_sample_if_missing=bool(data["use_sample_if_missing"]),
        output_dir=resolve_repo_path(Path(str(reports["output_dir"]))),
        json_name=str(reports["json_name"]),
        markdown_name=str(reports["markdown_name"]),
    )


def _load_registry_question(registry_path: Path, question_id: str) -> dict[str, Any]:
    registry = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    if not isinstance(registry, dict):
        raise ValueError(f"Causal question registry is not a mapping: {registry_path}")
    questions = registry.get("questions")
    if not isinstance(questions, list):
        raise ValueError(f"Causal question registry has no questions list: {registry_path}")
    for question in questions:
        if isinstance(question, dict) and question.get("id") == question_id:
            return question
    raise ValueError(f"Causal question registry has no question id: {question_id}")


def _tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError("Expected a list in causal workbench config.")
    return tuple(str(item) for item in value)


def _resolve_input_path(
    *,
    input_path: Path | None,
    config: CausalWorkbenchConfig,
) -> Path:
    if input_path is not None:
        return resolve_repo_path(input_path)
    if config.input_path is not None:
        return config.input_path
    integrated_path = build_ingest_paths(config.base_dir).integrated_person_year_parquet(
        config.data_year
    )
    if integrated_path.exists():
        return integrated_path
    if (
        config.use_sample_if_missing
        and config.sample_path is not None
        and config.sample_path.exists()
    ):
        return config.sample_path
    raise FileNotFoundError(
        "No processed integrated person-year table found. Build the pipeline first, "
        "set data.input_path in the causal config, or pass input_path explicitly."
    )


def _read_person_year_table(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Missing causal input table: {path}")
    if path.suffix == ".parquet":
        return pd.read_parquet(path)
    if path.suffix == ".csv":
        return pd.read_csv(path)
    raise ValueError(f"Unsupported causal input table format: {path.suffix}")


def _require_columns(frame: pd.DataFrame, required_columns: tuple[str, ...]) -> None:
    missing = [column for column in required_columns if column not in frame.columns]
    if missing:
        raise ValueError(f"Missing required columns for causal analysis: {missing}")


def _analysis_columns(config: CausalWorkbenchConfig) -> list[str]:
    columns = [
        config.treatment_column,
        config.outcome_column,
        config.sample_weight_column,
        *config.adjustment_columns,
    ]
    seen: set[str] = set()
    ordered: list[str] = []
    for column in columns:
        if column in seen:
            continue
        seen.add(column)
        ordered.append(column)
    return ordered


def _coerce_binary(series: pd.Series) -> pd.Series:
    mapped = series.map(_binary_value)
    return pd.Series(mapped, index=series.index, dtype="float64")


def _binary_value(value: object) -> float | None:
    if pd.isna(value):
        return None
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "t", "yes", "y", "1", "1.0"}:
            return 1.0
        if normalized in {"false", "f", "no", "n", "0", "0.0"}:
            return 0.0
        return None
    numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(numeric) or float(numeric) not in {0.0, 1.0}:
        return None
    return float(numeric)


def _coerce_sample_weights(frame: pd.DataFrame, weight_column: str) -> dict[str, float | int]:
    weights = pd.to_numeric(frame[weight_column], errors="coerce")
    weights = weights.where(weights > 0)
    missing_before = int(weights.isna().sum())
    observed = weights.dropna()
    fill_value = float(observed.median()) if not observed.empty else 1.0
    frame[weight_column] = weights.fillna(fill_value).astype("float64")
    return {
        "missing_or_nonpositive": missing_before,
        "fill_value": fill_value,
    }
