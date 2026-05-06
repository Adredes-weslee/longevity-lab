"""Dataset preparation for non-serving causal workbench analyses."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd  # type: ignore[import-untyped]
import yaml  # type: ignore[import-untyped]

from longevity_lab.causal.registry import (
    default_config_path_for_question,
    load_question_spec,
)
from longevity_lab.pipeline.ingest import build_ingest_paths

REPO_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True, slots=True)
class CausalWorkbenchConfig:
    """Configuration for one scripted causal analysis."""

    schema_version: int
    config_path: Path
    question_id: str
    title: str
    source_question_registry: Path
    treatment_name: str
    treatment_contrast: str
    treatment_column: str
    treatment_derivation: dict[str, Any]
    outcome_name: str
    outcome_timing: str
    outcome_column: str
    sample_weight_column: str
    required_columns: tuple[str, ...]
    adjustment_columns: tuple[str, ...]
    categorical_columns: tuple[str, ...]
    excluded_columns: tuple[str, ...]
    exclusion_rules: tuple[dict[str, Any], ...]
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


@dataclass(frozen=True, slots=True)
class _DerivedTreatment:
    values: pd.Series
    exclusion_masks: dict[str, pd.Series]


def default_smoking_lung_config_path() -> Path:
    """Return the repo-local smoking-to-lung-disease workbench config path."""
    return REPO_ROOT / "conf" / "causal" / "smoking_lung.yaml"


def load_smoking_lung_config(path: Path | None = None) -> CausalWorkbenchConfig:
    """Load the JSON-compatible config for the PR12 smoking causal prototype."""
    config_path = resolve_repo_path(path) if path else default_smoking_lung_config_path()
    return load_causal_workbench_config(config_path)


def load_causal_workbench_config(path: Path) -> CausalWorkbenchConfig:
    """Load one concrete causal workbench run config."""
    config_path = resolve_repo_path(path)
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Causal workbench config is not a mapping: {config_path}")
    return _config_from_payload(payload, config_path=config_path)


def load_causal_config_for_question(question_id_or_alias: str) -> CausalWorkbenchConfig:
    """Load the default concrete run config for a registry question id or alias."""
    return load_causal_workbench_config(default_config_path_for_question(question_id_or_alias))


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
    return prepare_causal_dataset(input_path=input_path, config=causal_config)


def prepare_causal_dataset(
    *,
    config: CausalWorkbenchConfig,
    input_path: Path | None = None,
) -> PreparedCausalDataset:
    """Prepare an analysis dataset for one configured non-serving causal question."""
    causal_config = config
    source_path = _resolve_input_path(input_path=input_path, config=causal_config)
    frame = _read_person_year_table(source_path)
    _require_columns(frame, causal_config.required_columns)

    input_rows = len(frame)
    working = frame.copy()
    derived_treatment = _derive_treatment(working, causal_config)
    working[causal_config.treatment_column] = derived_treatment.values
    working[causal_config.outcome_column] = _coerce_binary(working[causal_config.outcome_column])

    exclusions: dict[str, int] = {}
    for name, mask in derived_treatment.exclusion_masks.items():
        aligned = mask.reindex(working.index, fill_value=False)
        exclusions[name] = int(aligned.sum())
        working = working.loc[~aligned].copy()

    missing_treatment = working[causal_config.treatment_column].isna()
    exclusions["missing_treatment"] = int(missing_treatment.sum())
    working = working.loc[~missing_treatment].copy()

    missing_outcome = working[causal_config.outcome_column].isna()
    exclusions["missing_outcome"] = int(missing_outcome.sum())
    working = working.loc[~missing_outcome].copy()

    working = _apply_exclusion_rules(working, causal_config, exclusions)

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


def _config_from_payload(
    payload: dict[str, Any],
    *,
    config_path: Path,
) -> CausalWorkbenchConfig:
    columns = payload["columns"]
    diagnostics = payload["diagnostics"]
    data = payload["data"]
    reports = payload["reports"]
    estimator = payload["estimator"]
    registry_path = resolve_repo_path(Path(str(payload["source_question_registry"])))
    registry_question = load_question_spec(str(payload["question_id"]), path=registry_path)
    return CausalWorkbenchConfig(
        schema_version=int(payload["schema_version"]),
        config_path=config_path,
        question_id=registry_question.question_id,
        title=str(registry_question.title),
        source_question_registry=registry_path,
        treatment_name=str(registry_question.treatment_name),
        treatment_contrast=str(registry_question.treatment_contrast),
        treatment_column=str(columns["treatment"]),
        treatment_derivation=dict(payload.get("treatment_derivation", {"kind": "direct_binary"})),
        outcome_name=str(registry_question.outcome_name),
        outcome_timing=str(registry_question.outcome_timing),
        outcome_column=str(columns["outcome"]),
        sample_weight_column=str(columns["sample_weight"]),
        required_columns=_tuple(columns["required"]),
        adjustment_columns=_tuple(columns["adjustment"]),
        categorical_columns=_tuple(columns.get("categorical", [])),
        excluded_columns=_tuple(columns["excluded"]),
        exclusion_rules=_tuple_of_mappings(payload.get("exclusion_rules", [])),
        negative_control_outcomes=registry_question.negative_control_outcomes,
        negative_control_exposures=registry_question.negative_control_exposures,
        sensitivity_checks=registry_question.sensitivity_checks,
        dag_version=str(registry_question.dag_version),
        dag_edges=registry_question.dag_edges,
        residual_risks=registry_question.residual_risks,
        estimand=dict(registry_question.estimand),
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


def _tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError("Expected a list in causal workbench config.")
    return tuple(str(item) for item in value)


def _tuple_of_mappings(value: object) -> tuple[dict[str, Any], ...]:
    if not isinstance(value, list):
        raise ValueError("Expected a list of mappings in causal workbench config.")
    mappings: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            raise ValueError("Expected a mapping in causal workbench config.")
        mappings.append(dict(item))
    return tuple(mappings)


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


def _derive_treatment(frame: pd.DataFrame, config: CausalWorkbenchConfig) -> _DerivedTreatment:
    derivation = config.treatment_derivation
    kind = str(derivation.get("kind", "direct_binary"))
    if kind == "direct_binary":
        source_column = str(derivation.get("source_column", config.treatment_column))
        return _DerivedTreatment(
            values=_coerce_binary(frame[source_column]),
            exclusion_masks={},
        )
    if kind == "minimum_threshold":
        source_column = str(derivation["source_column"])
        threshold = float(derivation["threshold"])
        numeric = pd.to_numeric(frame[source_column], errors="coerce")
        values = pd.Series(pd.NA, index=frame.index, dtype="Float64")
        values = values.mask(numeric < threshold, 0.0)
        values = values.mask(numeric >= threshold, 1.0)
        return _DerivedTreatment(values=values.astype("float64"), exclusion_masks={})
    if kind == "bmi_obesity_vs_normal":
        source_column = str(derivation["source_column"])
        bmi = pd.to_numeric(frame[source_column], errors="coerce")
        normal_min = float(derivation.get("normal_min", 18.5))
        normal_max = float(derivation.get("normal_max", 25.0))
        obesity_min = float(derivation.get("obesity_min", 30.0))
        normal = (bmi >= normal_min) & (bmi < normal_max)
        obese = bmi >= obesity_min
        outside_contrast = bmi.notna() & ~(normal | obese)
        values = pd.Series(pd.NA, index=frame.index, dtype="Float64")
        values = values.mask(normal, 0.0)
        values = values.mask(obese, 1.0)
        return _DerivedTreatment(
            values=values.astype("float64"),
            exclusion_masks={"outside_bmi_obesity_vs_normal_contrast": outside_contrast},
        )
    if kind == "heavy_alcohol_by_sex":
        source_column = str(derivation["source_column"])
        sex_column = str(derivation.get("sex_column", "sex"))
        female_threshold = float(derivation.get("female_threshold", 7.0))
        male_threshold = float(derivation.get("male_threshold", 14.0))
        drinks = pd.to_numeric(frame[source_column], errors="coerce")
        sex = frame[sex_column].astype("string").str.lower()
        female = sex == "female"
        male = sex == "male"
        heavy = (female & (drinks > female_threshold)) | (male & (drinks > male_threshold))
        not_heavy = (female | male) & drinks.notna() & ~heavy
        values = pd.Series(pd.NA, index=frame.index, dtype="Float64")
        values = values.mask(not_heavy, 0.0)
        values = values.mask(heavy, 1.0)
        return _DerivedTreatment(values=values.astype("float64"), exclusion_masks={})
    raise ValueError(f"Unsupported causal treatment derivation kind: {kind}")


def _apply_exclusion_rules(
    frame: pd.DataFrame,
    config: CausalWorkbenchConfig,
    exclusions: dict[str, int],
) -> pd.DataFrame:
    working = frame
    for rule in config.exclusion_rules:
        kind = str(rule["kind"])
        name = str(rule.get("name", kind))
        if kind == "numeric_range":
            column = str(rule["column"])
            lower = float(rule["min"])
            upper = float(rule["max"])
            values = pd.to_numeric(working[column], errors="coerce")
            mask = values.isna() | (values < lower) | (values > upper)
        else:
            raise ValueError(f"Unsupported causal exclusion rule kind: {kind}")
        exclusions[name] = int(mask.sum())
        working = working.loc[~mask].copy()
    return working


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
