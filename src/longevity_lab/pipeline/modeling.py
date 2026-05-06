"""Training and evaluation utilities for Longevity Lab model bundles."""

from __future__ import annotations

import datetime as dt
import json
import re
import shutil
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, cast

import joblib  # type: ignore[import-untyped]
import numpy as np  # type: ignore[import-untyped]
import pandas as pd  # type: ignore[import-untyped]
from sklearn.base import BaseEstimator, TransformerMixin  # type: ignore[import-untyped]
from sklearn.calibration import CalibratedClassifierCV  # type: ignore[import-untyped]
from sklearn.ensemble import HistGradientBoostingClassifier  # type: ignore[import-untyped]
from sklearn.metrics import (  # type: ignore[import-untyped]
    average_precision_score,
    brier_score_loss,
    roc_auc_score,
)
from sklearn.model_selection import (  # type: ignore[import-untyped]
    StratifiedKFold,
    train_test_split,
)
from sklearn.pipeline import Pipeline  # type: ignore[import-untyped]
from sklearn.tree import DecisionTreeClassifier, export_text  # type: ignore[import-untyped]

from longevity_lab.artifacts.manifest import (
    ArtifactManifest,
    ConditionArtifact,
    ContextFeatureManifest,
    DatasetInfo,
    ExplanationArtifactManifest,
    save_manifest,
)
from longevity_lab.pipeline.common import default_data_dir
from longevity_lab.pipeline.ingest import build_ingest_paths

if TYPE_CHECKING:
    from optuna.trial import Trial  # type: ignore[import-untyped]


class SupportsMonotonicEstimator(Protocol):
    """Estimator methods needed for late-bound monotonic constraints."""

    def get_params(self, deep: bool = True) -> dict[str, object]:
        """Return estimator parameters."""

    def set_params(self, **params: object) -> SupportsMonotonicEstimator:
        """Set estimator parameters."""

    def fit(self, x: pd.DataFrame, y: object = None, **params: object) -> object:
        """Fit the estimator."""


FEATURE_LABELS: dict[str, str] = {
    "age": "Age",
    "bmi": "BMI",
    "smoker": "Smoking",
    "alcohol_servings_per_week": "Alcohol servings / week",
    "exercise_minutes_per_week": "Exercise minutes / week",
    "annual_aqi": "Annual AQI",
    "pm25_mean": "PM2.5 annual mean",
    "ozone_mean": "Ozone annual mean",
    "sex": "Sex",
    "race_ethnicity": "Race/ethnicity",
    "has_healthcare_coverage": "Healthcare coverage",
    "has_personal_doctor": "Personal doctor",
    "cost_barrier_to_care": "Could not see doctor due to cost",
    "last_checkup_within_year": "Checkup in past year",
    "sleep_hours_per_night": "Sleep hours / night",
    "physical_health_days": "Poor physical health days",
    "mental_health_days": "Poor mental health days",
    "acs_total_population": "ACS total population",
    "acs_poverty_percent": "ACS poverty percent",
    "acs_median_household_income": "ACS median household income",
    "acs_bachelors_degree_or_higher_percent": "ACS bachelors degree or higher",
    "acs_uninsured_percent": "ACS uninsured percent",
    "acs_disability_percent": "ACS disability percent",
    "acs_broadband_percent": "ACS broadband percent",
    "svi_overall_percentile": "SVI overall percentile",
    "svi_theme1_socioeconomic_percentile": "SVI socioeconomic percentile",
    "svi_theme2_household_characteristics_percentile": "SVI household percentile",
    "svi_theme3_racial_ethnic_minority_status_percentile": "SVI minority-status percentile",
    "svi_theme4_housing_transportation_percentile": "SVI housing/transportation percentile",
}

CONTEXT_JOIN_KEYS: tuple[str, str] = ("state_fips", "year")
CONTEXT_DEFAULT_LOOKUP_NAME = "context_state_year_lookup.json"
STATE_YEAR_CONTEXT_CAVEAT = (
    "State-year context is background geography context, not a personal behavior."
)

CATEGORICAL_FEATURES: frozenset[str] = frozenset({"sex", "race_ethnicity"})

BOOLEAN_FEATURES: frozenset[str] = frozenset(
    {
        "smoker",
        "has_healthcare_coverage",
        "has_personal_doctor",
        "cost_barrier_to_care",
        "last_checkup_within_year",
    }
)

SLICE_REPORT_COLUMNS: tuple[str, ...] = (
    "condition_id",
    "slice_dimension",
    "slice_value",
    "n_rows",
    "n_positive",
    "n_negative",
    "positive_rate",
    "mean_predicted_probability",
    "mean_predicted_probability_uncalibrated",
    "mean_predicted_probability_no_aqi",
    "calibration_gap",
    "average_precision",
    "roc_auc",
    "brier_score",
    "status",
)


@dataclass(frozen=True, slots=True)
class FeatureContractSpec:
    """Role metadata for the configured training feature contract."""

    version: str
    scenario_editable_features: tuple[str, ...]
    adjustment_features: tuple[str, ...]
    context_features: tuple[str, ...]
    sample_weight_column: str | None
    label_feature_exclusions: dict[str, tuple[str, ...]]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation for manifests and summaries."""
        return {
            "version": self.version,
            "scenario_editable_features": list(self.scenario_editable_features),
            "adjustment_features": list(self.adjustment_features),
            "context_features": list(self.context_features),
            "sample_weight_column": self.sample_weight_column,
            "label_feature_exclusions": {
                key: list(value) for key, value in self.label_feature_exclusions.items()
            },
        }


@dataclass(frozen=True, slots=True)
class TrainingSpec:
    """Concrete training configuration after Hydra parsing."""

    year: int
    base_data_dir: Path
    input_path: Path | None
    sample_path: Path
    use_sample_if_missing: bool
    artifacts_dir: Path
    bundle_id: str
    force_overwrite: bool
    notes: str | None
    features: tuple[str, ...]
    feature_contract: FeatureContractSpec
    conditions: dict[str, str]
    random_state: int
    test_size: float
    calibration_method: str
    calibration_cv: int
    prediction_sample_rows: int
    tuning_enabled: bool
    tuning_metric: str
    tuning_n_trials: int
    tuning_timeout_seconds: int | None
    tuning_cv_folds: int
    tuning_sample_size: int | None
    model_family: str
    model_params: dict[str, Any]
    model_monotonic_constraints: dict[str, int]
    model_criterion: str
    model_class_weight: str | dict[int, float] | None
    search_space: dict[str, dict[str, float | int]]
    git_commit: str | None


@dataclass(frozen=True, slots=True)
class ConditionTrainingResult:
    """Artifacts and summary metrics for one condition."""

    condition_id: str
    label_column: str
    pipeline_path: Path
    explanation_path: Path | None
    metrics_path: Path
    predictions_path: Path
    feature_importance_path: Path
    tree_text_path: Path
    shap_explanation_path: Path | None
    shap_skip_path: Path | None
    explanation_artifacts: tuple[ExplanationArtifactManifest, ...]
    uncertainty_path: Path | None
    metrics: dict[str, Any]


@dataclass(frozen=True, slots=True)
class TrainingBundleResult:
    """Bundle-level training outputs."""

    bundle_dir: Path
    dataset_path: Path
    manifest_path: Path
    training_summary_path: Path
    condition_results: list[ConditionTrainingResult]


class SampleWeightPipeline(Pipeline):
    """Pipeline variant that forwards top-level sample weights to the model step."""

    def fit(
        self,
        x: pd.DataFrame,
        y: pd.Series | None = None,
        sample_weight: pd.Series | np.ndarray | None = None,
        **params: object,
    ) -> SampleWeightPipeline:
        """Fit the pipeline while routing survey weights to the estimator."""
        if sample_weight is not None and "model__sample_weight" not in params:
            params["model__sample_weight"] = sample_weight
        return cast(SampleWeightPipeline, super().fit(x, y, **params))


class OptionalModelDependencyError(RuntimeError):
    """Raised when an optional model family dependency is not installed."""


class MonotonicConstraintPipeline(SampleWeightPipeline):
    """Two-step pipeline that derives estimator monotonic constraints after preprocessing."""

    def __init__(
        self,
        steps: list[tuple[str, object]],
        *,
        monotonic_constraints: Mapping[str, int] | None = None,
        memory: object | None = None,
        verbose: bool = False,
    ) -> None:
        """Store raw-feature constraints for cloneable sklearn calibration wrappers."""
        self.monotonic_constraints = monotonic_constraints
        super().__init__(steps=steps, memory=memory, verbose=verbose)

    def fit(
        self,
        x: pd.DataFrame,
        y: pd.Series | None = None,
        sample_weight: pd.Series | np.ndarray | None = None,
        **params: object,
    ) -> MonotonicConstraintPipeline:
        """Fit preprocessing first so raw constraints can map to transformed columns."""
        if not self.monotonic_constraints:
            return cast(
                MonotonicConstraintPipeline,
                super().fit(x, y, sample_weight=sample_weight, **params),
            )
        if len(self.steps) != 2 or self.steps[0][0] != "preprocess" or self.steps[1][0] != "model":
            raise ValueError("MonotonicConstraintPipeline expects preprocess and model steps.")

        preprocess_params, model_params = _split_pipeline_fit_params(params)
        preprocessor = cast(FeaturePreprocessor, self.named_steps["preprocess"])
        if preprocess_params:
            preprocessor.set_params(**preprocess_params)
        transformed = preprocessor.fit_transform(x, y)

        model = cast(SupportsMonotonicEstimator, self.named_steps["model"])
        constraints = monotonic_constraint_vector(
            tuple(str(name) for name in preprocessor.get_feature_names_out()),
            self.monotonic_constraints,
        )
        _set_estimator_monotonic_constraints(model, constraints)
        if sample_weight is not None and "sample_weight" not in model_params:
            model_params["sample_weight"] = sample_weight
        model.fit(transformed, y, **model_params)
        return self


class FeaturePreprocessor(BaseEstimator, TransformerMixin):
    """Select, impute, and encode the stable training feature contract."""

    def __init__(self, feature_names: tuple[str, ...]) -> None:
        """Store the ordered feature names."""
        self.feature_names = feature_names

    def fit(self, x: pd.DataFrame, y: pd.Series | None = None) -> FeaturePreprocessor:
        """Learn per-feature fill values from the training frame."""
        del y
        frame = self._coerce_frame(x)
        fill_values: dict[str, float] = {}
        categories: dict[str, tuple[str, ...]] = {}
        for feature_name in self.feature_names:
            if feature_name in CATEGORICAL_FEATURES:
                normalized = self._to_categorical(frame[feature_name])
                learned = tuple(sorted(set(normalized.dropna().tolist()) | {"missing"}))
                categories[feature_name] = learned
                continue
            series = self._to_numeric(frame[feature_name], feature_name)
            non_null = series.dropna()
            fill_values[feature_name] = float(non_null.median()) if not non_null.empty else 0.0
        self.fill_values_ = fill_values
        self.categories_ = categories
        self.transformed_feature_names_ = self._build_feature_names_out()
        return self

    def transform(self, x: pd.DataFrame) -> pd.DataFrame:
        """Return a numeric, imputed feature frame with stable column order."""
        if not hasattr(self, "fill_values_") or not hasattr(self, "categories_"):
            raise ValueError("FeaturePreprocessor must be fitted before transform().")
        frame = self._coerce_frame(x)
        transformed = pd.DataFrame(index=frame.index)
        fill_values = self.fill_values_
        categories = self.categories_
        for feature_name in self.feature_names:
            if feature_name in CATEGORICAL_FEATURES:
                normalized = self._to_categorical(frame[feature_name]).fillna("missing")
                known_categories = set(categories[feature_name])
                normalized = normalized.where(normalized.isin(known_categories), "missing")
                for category in categories[feature_name]:
                    column_name = self._one_hot_column_name(feature_name, category)
                    transformed[column_name] = (normalized == category).astype("float64")
            else:
                series = self._to_numeric(frame[feature_name], feature_name)
                transformed[feature_name] = series.fillna(fill_values[feature_name]).astype(
                    "float64"
                )
        return transformed

    def get_feature_names_out(self, input_features: list[str] | None = None) -> np.ndarray:
        """Return the stable feature names after preprocessing."""
        del input_features
        if not hasattr(self, "transformed_feature_names_"):
            return np.asarray(self.feature_names, dtype=object)
        return np.asarray(self.transformed_feature_names_, dtype=object)

    def _coerce_frame(self, x: pd.DataFrame) -> pd.DataFrame:
        if not isinstance(x, pd.DataFrame):
            raise TypeError("FeaturePreprocessor expects a pandas DataFrame.")
        missing = [name for name in self.feature_names if name not in x.columns]
        if missing:
            raise ValueError(f"Missing required feature columns: {missing}")
        return x.loc[:, list(self.feature_names)].copy()

    @staticmethod
    def _to_numeric(series: pd.Series, feature_name: str) -> pd.Series:
        if feature_name in BOOLEAN_FEATURES:
            return series.map(FeaturePreprocessor._to_boolean_float)
        return pd.to_numeric(series, errors="coerce")

    @staticmethod
    def _to_boolean_float(value: object) -> float:
        if pd.isna(value):
            return float("nan")
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "1", "yes", "y"}:
                return 1.0
            if normalized in {"false", "0", "no", "n"}:
                return 0.0
            return float("nan")
        if isinstance(value, (bool, np.bool_)):
            return float(bool(value))
        numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
        if pd.isna(numeric):
            return float("nan")
        return float(numeric != 0)

    @staticmethod
    def _to_categorical(series: pd.Series) -> pd.Series:
        normalized = series.astype("string").str.strip().str.lower()
        normalized = normalized.str.replace(r"[^a-z0-9]+", "_", regex=True).str.strip("_")
        return normalized.where(normalized.notna() & (normalized != ""), "missing")

    @staticmethod
    def _one_hot_column_name(feature_name: str, category: str) -> str:
        safe_category = re.sub(r"[^a-z0-9]+", "_", category.lower()).strip("_")
        return f"{feature_name}_{safe_category or 'missing'}"

    def _build_feature_names_out(self) -> tuple[str, ...]:
        names: list[str] = []
        categories = self.categories_
        for feature_name in self.feature_names:
            if feature_name in CATEGORICAL_FEATURES:
                names.extend(
                    self._one_hot_column_name(feature_name, category)
                    for category in categories[feature_name]
                )
            else:
                names.append(feature_name)
        return tuple(names)


def make_hist_gradient_boosting_pipeline(
    *,
    feature_names: tuple[str, ...],
    params: Mapping[str, Any],
    monotonic_constraints: Mapping[str, int] | None,
    random_state: int,
) -> SampleWeightPipeline:
    """Build a calibrated-benchmark-ready histogram GBDT pipeline."""
    model_params = dict(params)
    model_params.setdefault("random_state", random_state)
    model_params.setdefault("class_weight", "balanced")
    model = HistGradientBoostingClassifier(**model_params)
    return _make_tabular_model_pipeline(
        feature_names=feature_names,
        model=model,
        monotonic_constraints=monotonic_constraints,
    )


def make_xgboost_pipeline(
    *,
    feature_names: tuple[str, ...],
    params: Mapping[str, Any],
    monotonic_constraints: Mapping[str, int] | None,
    random_state: int,
    class_balance_scale: float | None,
) -> SampleWeightPipeline:
    """Build an optional XGBoost pipeline without importing xgboost at module import time."""
    xgb_classifier = _import_xgboost_classifier()
    model_params = dict(params)
    model_params.setdefault("objective", "binary:logistic")
    model_params.setdefault("eval_metric", "logloss")
    model_params.setdefault("tree_method", "hist")
    model_params.setdefault("random_state", random_state)
    model_params.setdefault("n_jobs", 1)
    if class_balance_scale is not None:
        model_params.setdefault("scale_pos_weight", class_balance_scale)
    model = xgb_classifier(**model_params)
    return _make_tabular_model_pipeline(
        feature_names=feature_names,
        model=model,
        monotonic_constraints=monotonic_constraints,
    )


def monotonic_constraint_vector(
    transformed_feature_names: Sequence[str],
    monotonic_constraints: Mapping[str, int] | None,
) -> tuple[int, ...]:
    """Map raw-feature monotonic constraints to transformed estimator columns."""
    if not monotonic_constraints:
        return tuple(0 for _ in transformed_feature_names)
    validated = _validate_monotonic_constraints(monotonic_constraints)
    return tuple(validated.get(feature_name, 0) for feature_name in transformed_feature_names)


def _make_tabular_model_pipeline(
    *,
    feature_names: tuple[str, ...],
    model: object,
    monotonic_constraints: Mapping[str, int] | None,
) -> SampleWeightPipeline:
    steps: list[tuple[str, object]] = [
        ("preprocess", FeaturePreprocessor(feature_names=feature_names)),
        ("model", model),
    ]
    if monotonic_constraints:
        return MonotonicConstraintPipeline(
            steps=steps,
            monotonic_constraints=_validate_monotonic_constraints(monotonic_constraints),
        )
    return SampleWeightPipeline(steps=steps)


def _validate_monotonic_constraints(
    monotonic_constraints: Mapping[str, int],
) -> dict[str, int]:
    validated: dict[str, int] = {}
    for feature_name, direction in monotonic_constraints.items():
        normalized = int(direction)
        if normalized not in {-1, 0, 1}:
            raise ValueError(
                f"Monotonic constraint for {feature_name!r} must be -1, 0, or 1 "
                f"(got {direction!r})."
            )
        validated[str(feature_name)] = normalized
    return validated


def _split_pipeline_fit_params(
    params: Mapping[str, object],
) -> tuple[dict[str, object], dict[str, object]]:
    preprocess_params: dict[str, object] = {}
    model_params: dict[str, object] = {}
    for name, value in params.items():
        if name.startswith("preprocess__"):
            preprocess_params[name.removeprefix("preprocess__")] = value
        elif name.startswith("model__"):
            model_params[name.removeprefix("model__")] = value
        else:
            model_params[name] = value
    return preprocess_params, model_params


def _set_estimator_monotonic_constraints(
    model: SupportsMonotonicEstimator,
    constraints: tuple[int, ...],
) -> None:
    params = model.get_params(deep=False)
    if "monotonic_cst" in params:
        model.set_params(monotonic_cst=list(constraints))
        return
    if "monotone_constraints" in params:
        model.set_params(monotone_constraints=constraints)
        return
    raise ValueError(f"Estimator {type(model).__name__} does not support monotonic constraints.")


def _import_xgboost_classifier() -> type[BaseEstimator]:
    try:
        from xgboost import XGBClassifier  # type: ignore[import-untyped]
    except ImportError as exc:
        raise OptionalModelDependencyError(
            "XGBoost support requires the optional train dependency. "
            "Install it with `pdm install -G train`."
        ) from exc
    return cast(type[BaseEstimator], XGBClassifier)


def build_training_spec(raw_cfg: dict[str, Any]) -> TrainingSpec:
    """Convert a Hydra config dict into a typed training spec."""
    data_cfg = raw_cfg["data"]
    artifacts_cfg = raw_cfg["artifacts"]
    training_cfg = raw_cfg["training"]
    tuning_cfg = raw_cfg["tuning"]
    model_cfg = raw_cfg["model"]
    bundle_id = raw_cfg.get("bundle_id") or dt.datetime.now(dt.UTC).strftime(
        "bundle-%Y%m%dT%H%M%SZ"
    )
    features = tuple(str(item) for item in raw_cfg["features"])
    return TrainingSpec(
        year=int(data_cfg["year"]),
        base_data_dir=Path(str(data_cfg["base_dir"])),
        input_path=Path(str(data_cfg["input_path"])) if data_cfg.get("input_path") else None,
        sample_path=Path(str(data_cfg["sample_path"])),
        use_sample_if_missing=bool(data_cfg["use_sample_if_missing"]),
        artifacts_dir=Path(str(artifacts_cfg["base_dir"])),
        bundle_id=str(bundle_id),
        force_overwrite=bool(artifacts_cfg["force_overwrite"]),
        notes=str(artifacts_cfg["notes"]) if artifacts_cfg.get("notes") else None,
        features=features,
        feature_contract=_build_feature_contract(raw_cfg, features=features),
        conditions={str(key): str(value) for key, value in dict(raw_cfg["conditions"]).items()},
        random_state=int(training_cfg["random_state"]),
        test_size=float(training_cfg["test_size"]),
        calibration_method=str(training_cfg["calibration_method"]),
        calibration_cv=int(training_cfg["calibration_cv"]),
        prediction_sample_rows=int(training_cfg["prediction_sample_rows"]),
        tuning_enabled=bool(tuning_cfg["enabled"]),
        tuning_metric=str(tuning_cfg["metric"]),
        tuning_n_trials=int(tuning_cfg["n_trials"]),
        tuning_timeout_seconds=(
            int(tuning_cfg["timeout_seconds"]) if tuning_cfg.get("timeout_seconds") else None
        ),
        tuning_cv_folds=int(tuning_cfg["cv_folds"]),
        tuning_sample_size=(
            int(tuning_cfg["sample_size"]) if tuning_cfg.get("sample_size") else None
        ),
        model_family=_model_family_from_config(model_cfg),
        model_params=_model_params_from_config(model_cfg),
        model_monotonic_constraints=_model_monotonic_constraints_from_config(model_cfg),
        model_criterion=str(model_cfg.get("criterion", "gini")),
        model_class_weight=model_cfg.get("class_weight"),
        search_space=_tree_search_space_from_config(model_cfg),
        git_commit=_detect_git_commit(),
    )


def _build_feature_contract(
    raw_cfg: dict[str, Any],
    *,
    features: tuple[str, ...],
) -> FeatureContractSpec:
    contract_cfg = raw_cfg.get("feature_contract")
    if not isinstance(contract_cfg, dict):
        return FeatureContractSpec(
            version="legacy_v1",
            scenario_editable_features=features,
            adjustment_features=(),
            context_features=(),
            sample_weight_column=None,
            label_feature_exclusions={},
        )
    contract = FeatureContractSpec(
        version=str(contract_cfg.get("version", "brfss_v2")),
        scenario_editable_features=tuple(
            str(item) for item in contract_cfg.get("scenario_editable_features", [])
        ),
        adjustment_features=tuple(
            str(item) for item in contract_cfg.get("adjustment_features", [])
        ),
        context_features=tuple(str(item) for item in contract_cfg.get("context_features", [])),
        sample_weight_column=(
            str(contract_cfg["sample_weight_column"])
            if contract_cfg.get("sample_weight_column")
            else None
        ),
        label_feature_exclusions={
            str(condition_id): tuple(str(item) for item in excluded_features)
            for condition_id, excluded_features in dict(
                contract_cfg.get("label_feature_exclusions", {})
            ).items()
        },
    )
    _validate_feature_contract(contract, features=features)
    return contract


def _validate_feature_contract(
    contract: FeatureContractSpec,
    *,
    features: tuple[str, ...],
) -> None:
    missing_context = sorted(set(contract.context_features) - set(features))
    if missing_context:
        raise ValueError(
            "feature_contract.context_features must be included in configured features: "
            f"{missing_context}"
        )


def _model_family_from_config(model_cfg: dict[str, Any]) -> str:
    """Return the configured training model family across legacy and benchmark configs."""
    return str(
        model_cfg.get("family") or model_cfg.get("kind") or model_cfg.get("name") or "decision_tree"
    )


def _model_params_from_config(model_cfg: dict[str, Any]) -> dict[str, Any]:
    """Return model-family parameters from benchmark-style configs when present."""
    params = model_cfg.get("params", {})
    return dict(params) if isinstance(params, dict) else {}


def _model_monotonic_constraints_from_config(model_cfg: dict[str, Any]) -> dict[str, int]:
    """Return validated monotonic constraints from model config."""
    raw_constraints = model_cfg.get("monotonic_constraints", {})
    if not isinstance(raw_constraints, dict):
        return {}
    return _validate_monotonic_constraints(
        {str(key): int(value) for key, value in raw_constraints.items()}
    )


def _tree_search_space_from_config(
    model_cfg: dict[str, Any],
) -> dict[str, dict[str, float | int]]:
    """Return decision-tree search space defaults for non-tree training configs."""
    default_space: dict[str, dict[str, float | int]] = {
        "max_depth": {"low": 2, "high": 8},
        "min_samples_split": {"low": 10, "high": 300},
        "min_samples_leaf": {"low": 5, "high": 120},
        "max_leaf_nodes": {"low": 4, "high": 80},
        "ccp_alpha": {"low": 0.00001, "high": 0.01},
    }
    search_space = model_cfg.get("search_space", default_space)
    if not isinstance(search_space, dict):
        return default_space
    return {str(key): dict(value) for key, value in search_space.items()}


def train_bundle(spec: TrainingSpec) -> TrainingBundleResult:
    """Train a calibrated per-condition bundle and write bundle artifacts."""
    data_frame, dataset_path = load_training_frame(spec)
    bundle_dir = spec.artifacts_dir / spec.bundle_id
    _prepare_bundle_dir(bundle_dir, force_overwrite=spec.force_overwrite)

    condition_results: list[ConditionTrainingResult] = []
    for condition_id, label_column in spec.conditions.items():
        result = _train_condition(
            data_frame,
            spec=spec,
            bundle_dir=bundle_dir,
            condition_id=condition_id,
            label_column=label_column,
        )
        condition_results.append(result)

    context_manifest = _write_context_feature_lookup(
        data_frame,
        spec=spec,
        bundle_dir=bundle_dir,
    )
    manifest = ArtifactManifest(
        dataset=_build_dataset_info(spec=spec, dataset_path=dataset_path),
        features=list(spec.features),
        context_features=context_manifest,
        conditions=[
            ConditionArtifact(
                condition_id=result.condition_id,
                pipeline_path=result.pipeline_path.name,
                explanation_path=(
                    result.explanation_path.name if result.explanation_path is not None else None
                ),
                metrics_path=result.metrics_path.name,
                explanation_method="tree_path",
                explanation_artifacts=list(result.explanation_artifacts),
                uncertainty_method=(
                    "calibration_interval" if result.uncertainty_path is not None else "none"
                ),
                uncertainty_path=(
                    result.uncertainty_path.name if result.uncertainty_path is not None else None
                ),
            )
            for result in condition_results
        ],
        git_commit=spec.git_commit,
        notes=spec.notes,
    )
    manifest_path = bundle_dir / "manifest.json"
    save_manifest(manifest, manifest_path)

    training_summary = {
        "bundle_id": spec.bundle_id,
        "dataset_path": dataset_path.as_posix(),
        "created_at": dt.datetime.now(dt.UTC).isoformat(),
        "git_commit": spec.git_commit,
        "features": list(spec.features),
        "feature_contract": spec.feature_contract.to_dict(),
        "context_features": context_manifest.model_dump() if context_manifest else None,
        "conditions": [
            {
                "condition_id": result.condition_id,
                "label_column": result.label_column,
                **result.metrics,
            }
            for result in condition_results
        ],
    }
    training_summary_path = bundle_dir / "training_summary.json"
    training_summary_path.write_text(
        json.dumps(training_summary, indent=2) + "\n",
        encoding="utf-8",
    )
    return TrainingBundleResult(
        bundle_dir=bundle_dir,
        dataset_path=dataset_path,
        manifest_path=manifest_path,
        training_summary_path=training_summary_path,
        condition_results=condition_results,
    )


def _write_context_feature_lookup(
    data_frame: pd.DataFrame,
    *,
    spec: TrainingSpec,
    bundle_dir: Path,
) -> ContextFeatureManifest | None:
    context_features = spec.feature_contract.context_features
    if not context_features:
        return None
    required = [*CONTEXT_JOIN_KEYS, *context_features]
    missing = [name for name in required if name not in data_frame.columns]
    if missing:
        raise ValueError(
            f"Context-aware training requires state-year join keys and context columns: {missing}"
        )

    lookup_frame = data_frame.loc[:, required].copy()
    lookup_frame["state_fips"] = lookup_frame["state_fips"].map(_normalize_state_fips)
    lookup_frame["year"] = pd.to_numeric(lookup_frame["year"], errors="coerce")
    if lookup_frame["state_fips"].isna().any() or lookup_frame["year"].isna().any():
        raise ValueError("Context lookup rows require non-null state_fips and year values.")
    lookup_frame["year"] = lookup_frame["year"].astype(int)
    unique_rows = lookup_frame.drop_duplicates().reset_index(drop=True)
    duplicate_keys = (
        unique_rows.groupby(list(CONTEXT_JOIN_KEYS), dropna=False)
        .size()
        .loc[lambda series: series > 1]
    )
    if not duplicate_keys.empty:
        raise ValueError(
            "Context features must be constant within each state-year key before packaging."
        )

    rows: list[dict[str, object]] = []
    for _, row in unique_rows.sort_values(list(CONTEXT_JOIN_KEYS)).iterrows():
        rows.append(
            {
                "state_fips": str(row["state_fips"]),
                "year": int(row["year"]),
                **{feature: _json_safe_scalar(row[feature]) for feature in context_features},
            }
        )

    lookup_path = bundle_dir / CONTEXT_DEFAULT_LOOKUP_NAME
    lookup_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "feature_names": list(context_features),
                "join_keys": list(CONTEXT_JOIN_KEYS),
                "rows": rows,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return ContextFeatureManifest(
        feature_names=list(context_features),
        source_ids=_context_source_ids(context_features),
        join_keys=list(CONTEXT_JOIN_KEYS),
        data_vintage=f"State-year ACS/SVI context aligned to BRFSS {spec.year}",
        lookup_path=lookup_path.name,
        default_values=_context_default_values(data_frame, context_features),
        caveats=[STATE_YEAR_CONTEXT_CAVEAT],
    )


def _context_source_ids(context_features: Sequence[str]) -> list[str]:
    source_ids: list[str] = []
    if any(feature.startswith("acs_") for feature in context_features):
        source_ids.append("census_acs5_api_context")
    if any(feature.startswith("svi_") for feature in context_features):
        source_ids.append("cdc_atsdr_svi_us_county_csv")
    return source_ids


def _context_default_values(
    frame: pd.DataFrame,
    context_features: Sequence[str],
) -> dict[str, int | float | str | bool | None]:
    defaults: dict[str, int | float | str | bool | None] = {}
    for feature in context_features:
        series = frame[feature]
        numeric = pd.to_numeric(series, errors="coerce")
        non_null_numeric = numeric.dropna()
        if not non_null_numeric.empty:
            defaults[feature] = _json_safe_scalar(float(non_null_numeric.median()))
            continue
        non_null = series.dropna()
        defaults[feature] = _json_safe_scalar(non_null.iloc[0]) if not non_null.empty else None
    return defaults


def _normalize_state_fips(value: object) -> str | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return f"{int(float(text)):02d}"
    except ValueError:
        return text.zfill(2) if text.isdigit() else None


def _json_safe_scalar(value: object) -> int | float | str | bool | None:
    if value is None or pd.isna(value):
        return None
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, bool | str):
        return value
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    if isinstance(value, int | float):
        return value
    return str(value)


def evaluate_bundle(bundle_dir: Path) -> pd.DataFrame:
    """Load per-condition metrics from an existing bundle."""
    manifest_path = bundle_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Missing manifest: {manifest_path}")
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    rows: list[dict[str, Any]] = []
    for condition in payload.get("conditions", []):
        metrics_path = bundle_dir / condition["metrics_path"]
        metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
        rows.append(
            {
                "condition_id": condition["condition_id"],
                "test_average_precision": metrics["calibrated_metrics"]["average_precision"],
                "test_roc_auc": metrics["calibrated_metrics"]["roc_auc"],
                "test_brier_score": metrics["calibrated_metrics"]["brier_score"],
                "test_average_precision_no_context": metrics.get(
                    "no_context_metrics",
                    {},
                ).get("average_precision"),
                "test_average_precision_no_aqi": metrics["no_aqi_metrics"]["average_precision"],
                "test_average_precision_no_pollutants": metrics.get(
                    "no_pollutants_metrics",
                    {},
                ).get("average_precision"),
                "positive_rate": metrics["target_positive_rate"],
            }
        )
    return pd.DataFrame(rows).sort_values("condition_id").reset_index(drop=True)


def evaluate_bundle_slices(bundle_dir: Path, *, min_rows: int = 200) -> pd.DataFrame:
    """Summarize per-slice metrics for each condition in a trained bundle."""
    manifest_path = bundle_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Missing manifest: {manifest_path}")
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    rows: list[dict[str, Any]] = []
    for condition in payload.get("conditions", []):
        condition_id = str(condition["condition_id"])
        predictions_path = bundle_dir / f"{condition_id}_predictions.parquet"
        if not predictions_path.exists():
            continue
        frame = pd.read_parquet(predictions_path)
        label_column = _infer_label_column(frame, condition_id=condition_id)
        rows.extend(
            _evaluate_prediction_slices(
                frame,
                condition_id=condition_id,
                label_column=label_column,
                min_rows=min_rows,
            )
        )
    if not rows:
        return pd.DataFrame(columns=list(SLICE_REPORT_COLUMNS))
    report = pd.DataFrame(rows)
    return report.sort_values(
        ["condition_id", "slice_dimension", "slice_value"],
        kind="stable",
    ).reset_index(drop=True)


def load_training_frame(spec: TrainingSpec) -> tuple[pd.DataFrame, Path]:
    """Load the integrated training table or the checked-in sample."""
    dataset_path = _resolve_dataset_path(spec)
    if dataset_path.suffix == ".parquet":
        frame = pd.read_parquet(dataset_path)
    else:
        frame = pd.read_csv(dataset_path)
    required = list(spec.features) + list(spec.conditions.values())
    if spec.feature_contract.sample_weight_column:
        required.append(spec.feature_contract.sample_weight_column)
    missing = [name for name in required if name not in frame.columns]
    if missing:
        raise ValueError(f"Training dataset is missing required columns: {missing}")
    return frame, dataset_path


def _features_for_condition(spec: TrainingSpec, *, condition_id: str) -> tuple[str, ...]:
    excluded = set(spec.feature_contract.label_feature_exclusions.get(condition_id, ()))
    return tuple(feature for feature in spec.features if feature not in excluded)


def _sample_weights_for_training(
    frame: pd.DataFrame,
    *,
    spec: TrainingSpec,
) -> pd.Series | None:
    column = spec.feature_contract.sample_weight_column
    if column is None:
        return None
    weights = pd.to_numeric(frame[column], errors="coerce")
    weights = weights.where(weights > 0)
    non_null = weights.dropna()
    fill_value = float(non_null.median()) if not non_null.empty else 1.0
    return weights.fillna(fill_value).astype("float64")


def _weighted_mean(values: pd.Series, *, sample_weight: pd.Series | None) -> float:
    numeric = pd.to_numeric(values, errors="coerce").astype("float64")
    if sample_weight is None:
        return float(numeric.mean())
    weights = pd.to_numeric(sample_weight, errors="coerce").astype("float64")
    valid = numeric.notna() & weights.notna() & (weights > 0)
    if not valid.any():
        return float(numeric.mean())
    return float(np.average(numeric.loc[valid], weights=weights.loc[valid]))


def default_base_data_dir() -> Path:
    """Expose the repo-root data dir for Hydra defaults and tests."""
    return default_data_dir()


def _evaluate_prediction_slices(
    frame: pd.DataFrame,
    *,
    condition_id: str,
    label_column: str,
    min_rows: int,
) -> list[dict[str, Any]]:
    slice_series_by_dimension = {
        "age_band": _bucket_age_band(frame["age"]),
        "bmi_band": _bucket_bmi_band(frame["bmi"]),
        "smoker_status": _bucket_smoker(frame["smoker"]),
        "aqi_tier": _bucket_aqi_tier(frame["annual_aqi"]),
        "exercise_tier": _bucket_exercise_tier(frame["exercise_minutes_per_week"]),
    }
    rows: list[dict[str, Any]] = []
    for slice_dimension, slice_series in slice_series_by_dimension.items():
        grouped = frame.assign(_slice_value=slice_series).groupby(
            "_slice_value", dropna=False, sort=True
        )
        for slice_value, slice_frame in grouped:
            rows.append(
                _slice_metrics_row(
                    slice_frame,
                    condition_id=condition_id,
                    label_column=label_column,
                    slice_dimension=slice_dimension,
                    slice_value=str(slice_value),
                    min_rows=min_rows,
                )
            )
    return rows


def _slice_metrics_row(
    frame: pd.DataFrame,
    *,
    condition_id: str,
    label_column: str,
    slice_dimension: str,
    slice_value: str,
    min_rows: int,
) -> dict[str, Any]:
    labels = pd.to_numeric(frame[label_column], errors="coerce")
    probabilities = pd.to_numeric(frame["predicted_probability"], errors="coerce")
    mask = labels.notna() & probabilities.notna()
    labels = labels.loc[mask].astype(int).reset_index(drop=True)
    probabilities = probabilities.loc[mask].astype(float).reset_index(drop=True)
    uncalibrated = (
        pd.to_numeric(frame.loc[mask, "predicted_probability_uncalibrated"], errors="coerce")
        .astype(float)
        .reset_index(drop=True)
        if "predicted_probability_uncalibrated" in frame.columns
        else None
    )
    no_aqi = (
        pd.to_numeric(frame.loc[mask, "predicted_probability_no_aqi"], errors="coerce")
        .astype(float)
        .reset_index(drop=True)
        if "predicted_probability_no_aqi" in frame.columns
        else None
    )

    n_rows = int(len(labels))
    n_positive = int(labels.sum()) if n_rows else 0
    n_negative = n_rows - n_positive
    positive_rate = float(labels.mean()) if n_rows else None
    mean_probability = float(probabilities.mean()) if n_rows else None
    mean_probability_uncalibrated = (
        float(uncalibrated.mean()) if uncalibrated is not None and n_rows else None
    )
    mean_probability_no_aqi = float(no_aqi.mean()) if no_aqi is not None and n_rows else None
    calibration_gap = (
        abs(mean_probability - positive_rate)
        if mean_probability is not None and positive_rate is not None
        else None
    )

    status = "ok"
    if n_rows < min_rows:
        status = "too_small"
    elif len(labels.unique()) < 2:
        status = "single_class"

    metrics: dict[str, float | None] = {
        "average_precision": None,
        "roc_auc": None,
        "brier_score": None,
    }
    if status == "ok":
        metrics = _binary_metrics(labels, probabilities.to_numpy())

    return {
        "condition_id": condition_id,
        "slice_dimension": slice_dimension,
        "slice_value": slice_value,
        "n_rows": n_rows,
        "n_positive": n_positive,
        "n_negative": n_negative,
        "positive_rate": positive_rate,
        "mean_predicted_probability": mean_probability,
        "mean_predicted_probability_uncalibrated": mean_probability_uncalibrated,
        "mean_predicted_probability_no_aqi": mean_probability_no_aqi,
        "calibration_gap": calibration_gap,
        "average_precision": metrics["average_precision"],
        "roc_auc": metrics["roc_auc"],
        "brier_score": metrics["brier_score"],
        "status": status,
    }


def _infer_label_column(frame: pd.DataFrame, *, condition_id: str) -> str:
    label_columns = [name for name in frame.columns if name.startswith("label_")]
    if len(label_columns) != 1:
        raise ValueError(
            f"Expected exactly one label column in prediction frame for {condition_id}, "
            f"got {label_columns}."
        )
    return str(label_columns[0])


def _bucket_age_band(values: pd.Series) -> pd.Series:
    age = pd.to_numeric(values, errors="coerce")
    binned = pd.cut(
        age,
        bins=[-np.inf, 35, 50, 65, np.inf],
        labels=["18-34", "35-49", "50-64", "65+"],
        right=False,
    )
    return _categorical_with_missing(binned)


def _bucket_bmi_band(values: pd.Series) -> pd.Series:
    bmi = pd.to_numeric(values, errors="coerce")
    binned = pd.cut(
        bmi,
        bins=[-np.inf, 25, 30, np.inf],
        labels=["<25", "25-29.9", "30+"],
        right=False,
    )
    return _categorical_with_missing(binned)


def _bucket_smoker(values: pd.Series) -> pd.Series:
    mapped = values.map(
        lambda value: "Missing" if pd.isna(value) else ("Smoker" if bool(value) else "Non-smoker")
    )
    return mapped.astype("string")


def _bucket_aqi_tier(values: pd.Series) -> pd.Series:
    aqi = pd.to_numeric(values, errors="coerce")
    binned = pd.cut(
        aqi,
        bins=[-np.inf, 51, 101, np.inf],
        labels=["<=50", "51-100", "101+"],
        right=False,
    )
    return _categorical_with_missing(binned)


def _bucket_exercise_tier(values: pd.Series) -> pd.Series:
    exercise = pd.to_numeric(values, errors="coerce")
    binned = pd.cut(
        exercise,
        bins=[-np.inf, 1, 150, np.inf],
        labels=["0", "1-149", "150+"],
        right=False,
    )
    return _categorical_with_missing(binned)


def _categorical_with_missing(values: pd.Series) -> pd.Series:
    series = values.astype("object")
    return series.where(pd.notna(series), "Missing").astype("string")


def _resolve_dataset_path(spec: TrainingSpec) -> Path:
    if spec.input_path is not None:
        if not spec.input_path.exists():
            raise FileNotFoundError(f"Configured input_path does not exist: {spec.input_path}")
        return spec.input_path

    paths = build_ingest_paths(spec.base_data_dir)
    integrated_path = paths.integrated_person_year_parquet(spec.year)
    if integrated_path.exists():
        return integrated_path

    if spec.use_sample_if_missing and spec.sample_path.exists():
        return spec.sample_path

    raise FileNotFoundError(
        "No integrated training table found. Build the pipeline first or point data.input_path to "
        "a CSV/Parquet file."
    )


def _prepare_bundle_dir(bundle_dir: Path, *, force_overwrite: bool) -> None:
    if bundle_dir.exists():
        if not force_overwrite:
            raise FileExistsError(
                f"Bundle already exists: {bundle_dir}. Use a new bundle_id or force overwrite."
            )
        shutil.rmtree(bundle_dir)
    bundle_dir.mkdir(parents=True, exist_ok=True)


def _train_condition(
    data_frame: pd.DataFrame,
    *,
    spec: TrainingSpec,
    bundle_dir: Path,
    condition_id: str,
    label_column: str,
) -> ConditionTrainingResult:
    condition_features = _features_for_condition(spec, condition_id=condition_id)
    feature_frame = data_frame.loc[:, list(condition_features)].copy()
    labels = pd.to_numeric(data_frame[label_column], errors="coerce")
    mask = labels.notna()
    feature_frame = feature_frame.loc[mask].reset_index(drop=True)
    label_series = labels.loc[mask].astype(int).reset_index(drop=True)
    sample_weights = _sample_weights_for_training(data_frame, spec=spec)
    sample_weights = (
        sample_weights.loc[mask].reset_index(drop=True) if sample_weights is not None else None
    )
    _validate_binary_target(label_series, condition_id=condition_id)

    split_values = train_test_split(
        feature_frame,
        label_series,
        sample_weights if sample_weights is not None else pd.Series(1.0, index=label_series.index),
        test_size=spec.test_size,
        random_state=spec.random_state,
        stratify=label_series,
    )
    x_train, x_test, y_train, y_test, w_train, w_test = split_values

    sample_weight_train = w_train if sample_weights is not None else None
    sample_weight_test = w_test if sample_weights is not None else None

    tuned_params = _tune_tree_params(
        x_train,
        y_train,
        spec=spec,
        feature_names=condition_features,
        sample_weight=sample_weight_train,
    )
    explanation_pipeline = _make_training_pipeline(
        condition_features,
        spec=spec,
        overrides=tuned_params,
    )
    explanation_pipeline.fit(x_train, y_train, sample_weight=sample_weight_train)

    calibrated_pipeline = _fit_calibrated_pipeline(
        x_train,
        y_train,
        spec=spec,
        overrides=tuned_params,
        feature_names=condition_features,
        sample_weight=sample_weight_train,
    )
    base_probabilities = _predict_positive_class(explanation_pipeline, x_test)
    calibrated_probabilities = _predict_positive_class(calibrated_pipeline, x_test)
    calibrated_metrics = _binary_metrics(
        y_test,
        calibrated_probabilities,
        sample_weight=sample_weight_test,
    )
    base_metrics = _binary_metrics(y_test, base_probabilities, sample_weight=sample_weight_test)

    no_aqi_metrics, no_aqi_probabilities = _fit_feature_ablation(
        x_train,
        x_test,
        y_train,
        y_test,
        spec=spec,
        tuned_params=tuned_params,
        feature_names=condition_features,
        drop_features=("annual_aqi",),
        fallback_probabilities=calibrated_probabilities,
        fallback_metrics=calibrated_metrics,
        sample_weight_train=sample_weight_train,
        sample_weight_test=sample_weight_test,
    )
    no_pollutants_metrics, no_pollutants_probabilities = _fit_feature_ablation(
        x_train,
        x_test,
        y_train,
        y_test,
        spec=spec,
        tuned_params=tuned_params,
        feature_names=condition_features,
        drop_features=("pm25_mean", "ozone_mean"),
        fallback_probabilities=calibrated_probabilities,
        fallback_metrics=calibrated_metrics,
        sample_weight_train=sample_weight_train,
        sample_weight_test=sample_weight_test,
    )
    no_context_metrics, no_context_probabilities = _fit_feature_ablation(
        x_train,
        x_test,
        y_train,
        y_test,
        spec=spec,
        tuned_params=tuned_params,
        feature_names=condition_features,
        drop_features=spec.feature_contract.context_features,
        fallback_probabilities=calibrated_probabilities,
        fallback_metrics=calibrated_metrics,
        sample_weight_train=sample_weight_train,
        sample_weight_test=sample_weight_test,
    )

    positive_rate = _weighted_mean(y_test.astype(float), sample_weight=sample_weight_test)

    condition_prefix = condition_id
    pipeline_path = bundle_dir / f"{condition_prefix}.joblib"
    explanation_path = bundle_dir / f"{condition_prefix}_explanation.joblib"
    metrics_path = bundle_dir / f"{condition_prefix}_metrics.json"
    predictions_path = bundle_dir / f"{condition_prefix}_predictions.parquet"
    feature_importance_path = bundle_dir / f"{condition_prefix}_feature_importances.json"
    tree_text_path = bundle_dir / f"{condition_prefix}_tree.txt"
    uncertainty_path = bundle_dir / f"{condition_prefix}_uncertainty.json"

    joblib.dump(calibrated_pipeline, pipeline_path)
    tree_explanation_path: Path | None = None
    if _supports_tree_path_explanations(explanation_pipeline):
        joblib.dump(explanation_pipeline, explanation_path)
        tree_explanation_path = explanation_path

    test_predictions = x_test.copy()
    test_predictions[label_column] = y_test.to_numpy()
    test_predictions["predicted_probability"] = calibrated_probabilities
    test_predictions["predicted_probability_uncalibrated"] = base_probabilities
    test_predictions["predicted_probability_no_aqi"] = no_aqi_probabilities
    test_predictions["predicted_probability_no_pollutants"] = no_pollutants_probabilities
    test_predictions["predicted_probability_no_context"] = no_context_probabilities
    if sample_weight_test is not None:
        test_predictions[spec.feature_contract.sample_weight_column or "survey_weight"] = (
            sample_weight_test.to_numpy()
        )
    if len(test_predictions) > spec.prediction_sample_rows:
        test_predictions = test_predictions.sample(
            n=spec.prediction_sample_rows,
            random_state=spec.random_state,
        )
    test_predictions.to_parquet(predictions_path, index=False)

    importances = _feature_importances(explanation_pipeline)
    feature_importance_path.write_text(json.dumps(importances, indent=2) + "\n", encoding="utf-8")

    tree_text = _tree_text_or_model_summary(explanation_pipeline)
    tree_text_path.write_text(tree_text + "\n", encoding="utf-8")
    shap_explanation_path, shap_skip_path, shap_record = _write_shap_explanation_artifact(
        explanation_pipeline,
        x_train,
        bundle_dir=bundle_dir,
        condition_id=condition_id,
        random_state=spec.random_state,
    )
    explanation_artifacts: list[ExplanationArtifactManifest] = []
    if tree_explanation_path is not None:
        explanation_artifacts.append(
            ExplanationArtifactManifest(
                method="tree_path",
                artifact_path=tree_explanation_path.name,
                feature_names=list(
                    explanation_pipeline.named_steps["preprocess"].get_feature_names_out()
                ),
                caveats=[
                    "Decision-tree rule-path split; direction compares branch positive-class "
                    "risk, not a causal effect.",
                ],
            ),
        )
    if shap_record is not None:
        explanation_artifacts.append(shap_record)
    written_uncertainty_path, uncertainty_metrics = _write_calibration_interval_artifact(
        y_test,
        calibrated_probabilities,
        sample_weight=sample_weight_test,
        artifact_path=uncertainty_path,
    )

    metrics_payload = {
        "condition_id": condition_id,
        "label_column": label_column,
        "features": list(condition_features),
        "context_features": [
            feature
            for feature in condition_features
            if feature in spec.feature_contract.context_features
        ],
        "context_feature_count": sum(
            1 for feature in condition_features if feature in spec.feature_contract.context_features
        ),
        "sample_weight_column": spec.feature_contract.sample_weight_column,
        "rows_total": int(len(feature_frame)),
        "rows_train": int(len(x_train)),
        "rows_test": int(len(x_test)),
        "weighted_rows_train": (
            float(sample_weight_train.sum())
            if sample_weight_train is not None
            else int(len(x_train))
        ),
        "weighted_rows_test": (
            float(sample_weight_test.sum()) if sample_weight_test is not None else int(len(x_test))
        ),
        "target_positive_rate": positive_rate,
        "best_params": tuned_params,
        "base_metrics": base_metrics,
        "calibrated_metrics": calibrated_metrics,
        "no_context_metrics": no_context_metrics,
        "no_aqi_metrics": no_aqi_metrics,
        "no_pollutants_metrics": no_pollutants_metrics,
        "shap_explanation": _shap_explanation_metric_payload(
            shap_explanation_path=shap_explanation_path,
            shap_skip_path=shap_skip_path,
            shap_record=shap_record,
        ),
        "uncertainty": uncertainty_metrics,
    }
    metrics_path.write_text(json.dumps(metrics_payload, indent=2) + "\n", encoding="utf-8")

    return ConditionTrainingResult(
        condition_id=condition_id,
        label_column=label_column,
        pipeline_path=pipeline_path,
        explanation_path=tree_explanation_path,
        metrics_path=metrics_path,
        predictions_path=predictions_path,
        feature_importance_path=feature_importance_path,
        tree_text_path=tree_text_path,
        shap_explanation_path=shap_explanation_path,
        shap_skip_path=shap_skip_path,
        explanation_artifacts=tuple(explanation_artifacts),
        uncertainty_path=written_uncertainty_path,
        metrics=metrics_payload,
    )


def _write_shap_explanation_artifact(
    pipeline: Pipeline,
    training_frame: pd.DataFrame,
    *,
    bundle_dir: Path,
    condition_id: str,
    random_state: int,
    background_sample_size: int = 128,
) -> tuple[Path | None, Path | None, ExplanationArtifactManifest | None]:
    """Persist compact TreeSHAP serving metadata for supported tree-ensemble pipelines."""
    if not _supports_tree_shap(pipeline):
        skip_path = bundle_dir / f"{condition_id}_shap_explanation_skipped.json"
        skip_path.write_text(
            json.dumps(
                {
                    "status": "skipped",
                    "reason": (
                        "TreeSHAP packaging is not applicable to the decision-tree "
                        "rule-path baseline."
                    ),
                    "model_type": type(pipeline.named_steps.get("model")).__name__,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return None, skip_path, None
    if not _shap_dependency_available():
        skip_path = bundle_dir / f"{condition_id}_shap_explanation_skipped.json"
        skip_path.write_text(
            json.dumps(
                {
                    "status": "skipped",
                    "reason": "Optional SHAP dependency is not installed.",
                    "install": "pdm install -G explainability",
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return None, skip_path, None

    sample_size = min(background_sample_size, len(training_frame))
    background = training_frame.sample(n=sample_size, random_state=random_state).reset_index(
        drop=True
    )
    feature_names = [
        str(item) for item in pipeline.named_steps["preprocess"].get_feature_names_out()
    ]
    artifact_path = bundle_dir / f"{condition_id}_shap_explanation.joblib"
    caveat = (
        "TreeSHAP attribution from a compact training background sample; correlated "
        "features can share attribution."
    )
    joblib.dump(
        {
            "kind": "tree_shap",
            "pipeline": pipeline,
            "background": background,
            "feature_names": feature_names,
            "caveats": [caveat],
        },
        artifact_path,
    )
    return (
        artifact_path,
        None,
        ExplanationArtifactManifest(
            method="shap",
            artifact_path=artifact_path.name,
            background_sample_size=sample_size,
            feature_names=feature_names,
            caveats=[caveat],
        ),
    )


def _tree_text_or_model_summary(pipeline: Pipeline) -> str:
    """Return decision-tree text when available, otherwise a compact model-family summary."""
    model = pipeline.named_steps["model"]
    if isinstance(model, DecisionTreeClassifier):
        return cast(
            str,
            export_text(
                model,
                feature_names=list(pipeline.named_steps["preprocess"].get_feature_names_out()),
            ),
        )
    return (
        f"{type(model).__name__} does not expose a single decision-tree rule path. "
        "Use manifest-declared explanation artifacts for model-matched explanations."
    )


def _supports_tree_path_explanations(pipeline: Pipeline) -> bool:
    """Return whether a fitted pipeline exposes scikit-learn decision-tree path APIs."""
    model = pipeline.named_steps.get("model")
    return all(hasattr(model, name) for name in ("decision_path", "tree_", "apply"))


def _supports_tree_shap(pipeline: Pipeline) -> bool:
    """Return whether a fitted pipeline's model family should opt into TreeSHAP packaging."""
    model = pipeline.named_steps.get("model")
    model_type = str(type(model).__name__)
    return model_type in {
        "HistGradientBoostingClassifier",
        "GradientBoostingClassifier",
        "RandomForestClassifier",
        "ExtraTreesClassifier",
        "XGBClassifier",
    }


def _shap_dependency_available() -> bool:
    """Return whether the optional SHAP dependency can be imported."""
    try:
        import shap  # type: ignore[import-not-found, unused-ignore]
    except ImportError:
        return False
    return shap is not None


def _shap_explanation_metric_payload(
    *,
    shap_explanation_path: Path | None,
    shap_skip_path: Path | None,
    shap_record: ExplanationArtifactManifest | None,
) -> dict[str, Any]:
    """Return truthful metrics metadata for SHAP packaging status."""
    if shap_explanation_path is not None and shap_record is not None:
        return {
            "status": "available",
            "artifact_path": shap_explanation_path.name,
            "background_sample_size": shap_record.background_sample_size,
        }
    reason = "TreeSHAP packaging was skipped."
    if shap_skip_path is not None and shap_skip_path.exists():
        payload = json.loads(shap_skip_path.read_text(encoding="utf-8"))
        if isinstance(payload, dict) and payload.get("reason"):
            reason = str(payload["reason"])
    return {
        "status": "skipped",
        "artifact_path": shap_skip_path.name if shap_skip_path is not None else None,
        "reason": reason,
    }


def _write_calibration_interval_artifact(
    y_true: pd.Series,
    probabilities: np.ndarray,
    *,
    sample_weight: pd.Series | None,
    artifact_path: Path,
    confidence_level: float = 0.9,
    min_rows: int = 30,
) -> tuple[Path | None, dict[str, Any]]:
    """Persist a held-out empirical calibration interval artifact when support is adequate."""
    if len(y_true) < min_rows or len(np.unique(y_true)) < 2:
        return None, {
            "status": "skipped",
            "reason": (
                "Held-out uncertainty intervals require at least "
                f"{min_rows} rows and both outcome classes."
            ),
            "n_calibration": int(len(y_true)),
        }
    labels = y_true.astype(float).to_numpy()
    clipped_probabilities = np.clip(np.asarray(probabilities, dtype=float), 0.0, 1.0)
    residuals = np.abs(labels - clipped_probabilities)
    weights = _normalized_weight_array(sample_weight, expected_length=len(residuals))
    half_width = float(_weighted_quantile(residuals, confidence_level, sample_weight=weights))
    empirical_coverage = float(_weighted_mean_array(residuals <= half_width, sample_weight=weights))
    diagnostics = _calibration_diagnostics(
        labels,
        clipped_probabilities,
        sample_weight=weights,
    )
    caveat = (
        "Held-out empirical calibration interval from absolute prediction residuals; it summarizes "
        "model uncertainty for communication and is not an individual clinical confidence interval."
    )
    payload: dict[str, Any] = {
        "method": "calibration_interval",
        "source": "heldout_absolute_residual_quantile",
        "half_width": round(half_width, 6),
        "confidence_level": confidence_level,
        "n_calibration": int(len(y_true)),
        "empirical_coverage": round(empirical_coverage, 6),
        "diagnostics": diagnostics,
        "caveat": caveat,
    }
    artifact_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return artifact_path, {
        "status": "available",
        "artifact_path": artifact_path.name,
        "method": payload["method"],
        "source": payload["source"],
        "half_width": payload["half_width"],
        "confidence_level": payload["confidence_level"],
        "n_calibration": payload["n_calibration"],
        "empirical_coverage": payload["empirical_coverage"],
        "diagnostics": diagnostics,
    }


def _calibration_diagnostics(
    labels: np.ndarray,
    probabilities: np.ndarray,
    *,
    sample_weight: np.ndarray | None,
    n_bins: int = 10,
) -> dict[str, float]:
    """Return compact calibration diagnostics for model cards and uncertainty payloads."""
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    expected_calibration_error = 0.0
    max_calibration_gap = 0.0
    total_weight = _total_weight(labels, sample_weight=sample_weight)
    for index in range(n_bins):
        left = bins[index]
        right = bins[index + 1]
        if index == n_bins - 1:
            mask = (probabilities >= left) & (probabilities <= right)
        else:
            mask = (probabilities >= left) & (probabilities < right)
        if not bool(mask.any()):
            continue
        bin_weight = _total_weight(labels[mask], sample_weight=_masked_weights(sample_weight, mask))
        observed = _weighted_mean_array(
            labels[mask], sample_weight=_masked_weights(sample_weight, mask)
        )
        predicted = _weighted_mean_array(
            probabilities[mask],
            sample_weight=_masked_weights(sample_weight, mask),
        )
        gap = abs(float(predicted) - float(observed))
        expected_calibration_error += (bin_weight / total_weight) * gap
        max_calibration_gap = max(max_calibration_gap, gap)
    return {
        "expected_calibration_error": round(float(expected_calibration_error), 6),
        "max_calibration_gap": round(float(max_calibration_gap), 6),
        "mean_absolute_error": round(
            float(
                _weighted_mean_array(np.abs(labels - probabilities), sample_weight=sample_weight)
            ),
            6,
        ),
        "brier_score": round(
            float(_weighted_mean_array((labels - probabilities) ** 2, sample_weight=sample_weight)),
            6,
        ),
    }


def _normalized_weight_array(
    sample_weight: pd.Series | None,
    *,
    expected_length: int,
) -> np.ndarray | None:
    if sample_weight is None:
        return None
    weights = sample_weight.astype(float).to_numpy()
    if len(weights) != expected_length:
        raise ValueError(
            f"sample_weight length {len(weights)} does not match expected {expected_length}."
        )
    if not np.all(np.isfinite(weights)) or float(weights.sum()) <= 0.0:
        return None
    return cast(np.ndarray, weights)


def _weighted_quantile(
    values: np.ndarray,
    quantile: float,
    *,
    sample_weight: np.ndarray | None,
) -> float:
    clipped_quantile = min(max(float(quantile), 0.0), 1.0)
    if sample_weight is None:
        return float(np.quantile(values, clipped_quantile))
    order = np.argsort(values)
    sorted_values = values[order]
    sorted_weights = sample_weight[order]
    cumulative = np.cumsum(sorted_weights) / float(sorted_weights.sum())
    index = int(np.searchsorted(cumulative, clipped_quantile, side="left"))
    return float(sorted_values[min(index, len(sorted_values) - 1)])


def _weighted_mean_array(
    values: np.ndarray,
    *,
    sample_weight: np.ndarray | None,
) -> float:
    numeric_values = np.asarray(values, dtype=float)
    if sample_weight is None:
        return float(np.mean(numeric_values))
    return float(np.average(numeric_values, weights=sample_weight))


def _total_weight(values: np.ndarray, *, sample_weight: np.ndarray | None) -> float:
    if sample_weight is None:
        return float(len(values))
    return float(sample_weight.sum())


def _masked_weights(sample_weight: np.ndarray | None, mask: np.ndarray) -> np.ndarray | None:
    if sample_weight is None:
        return None
    return cast(np.ndarray, sample_weight[mask])


def _fit_feature_ablation(
    x_train: pd.DataFrame,
    x_test: pd.DataFrame,
    y_train: pd.Series,
    y_test: pd.Series,
    *,
    spec: TrainingSpec,
    tuned_params: dict[str, Any],
    feature_names: tuple[str, ...],
    drop_features: tuple[str, ...],
    fallback_probabilities: np.ndarray,
    fallback_metrics: dict[str, float | None],
    sample_weight_train: pd.Series | None,
    sample_weight_test: pd.Series | None,
) -> tuple[dict[str, float | None], np.ndarray]:
    ablation_features = tuple(feature for feature in feature_names if feature not in drop_features)
    if ablation_features == feature_names:
        return dict(fallback_metrics), fallback_probabilities.copy()
    ablation_pipeline = _fit_calibrated_pipeline(
        x_train.loc[:, list(ablation_features)],
        y_train,
        spec=spec,
        overrides=tuned_params,
        feature_names=ablation_features,
        sample_weight=sample_weight_train,
    )
    probabilities = _predict_positive_class(
        ablation_pipeline,
        x_test.loc[:, list(ablation_features)],
    )
    return _binary_metrics(y_test, probabilities, sample_weight=sample_weight_test), probabilities


def _make_training_pipeline(
    feature_names: tuple[str, ...],
    *,
    spec: TrainingSpec,
    overrides: dict[str, Any] | None = None,
) -> SampleWeightPipeline:
    if spec.model_family == "hist_gradient_boosting":
        params: dict[str, Any] = dict(spec.model_params)
        if overrides:
            params.update(overrides)
        params.setdefault("max_iter", 20)
        params.setdefault("min_samples_leaf", 20)
        return make_hist_gradient_boosting_pipeline(
            feature_names=feature_names,
            params=params,
            monotonic_constraints=spec.model_monotonic_constraints,
            random_state=spec.random_state,
        )
    if spec.model_family != "decision_tree":
        raise ValueError(f"Unsupported training model family: {spec.model_family}")
    params = {
        "criterion": spec.model_criterion,
        "class_weight": spec.model_class_weight,
        "random_state": spec.random_state,
    }
    if overrides:
        params.update(overrides)
    return SampleWeightPipeline(
        steps=[
            ("preprocess", FeaturePreprocessor(feature_names=feature_names)),
            ("model", DecisionTreeClassifier(**params)),
        ]
    )


def _fit_calibrated_pipeline(
    x_train: pd.DataFrame,
    y_train: pd.Series,
    *,
    spec: TrainingSpec,
    overrides: dict[str, Any],
    feature_names: tuple[str, ...] | None = None,
    sample_weight: pd.Series | None = None,
) -> CalibratedClassifierCV | Pipeline:
    base_pipeline = _make_training_pipeline(
        feature_names or spec.features,
        spec=spec,
        overrides=overrides,
    )
    calibration_folds = _safe_cv_folds(y_train, requested_folds=spec.calibration_cv)
    if calibration_folds < 2:
        base_pipeline.fit(x_train, y_train, sample_weight=sample_weight)
        return base_pipeline
    calibrated = CalibratedClassifierCV(
        estimator=base_pipeline,
        method=spec.calibration_method,
        cv=calibration_folds,
    )
    calibrated.fit(x_train, y_train, sample_weight=sample_weight)
    return calibrated


def _tune_tree_params(
    x_train: pd.DataFrame,
    y_train: pd.Series,
    *,
    spec: TrainingSpec,
    feature_names: tuple[str, ...],
    sample_weight: pd.Series | None,
) -> dict[str, Any]:
    if not spec.tuning_enabled:
        return {}
    if spec.model_family != "decision_tree":
        return {}

    try:
        import optuna  # type: ignore[import-untyped]
    except (
        ImportError
    ) as exc:  # pragma: no cover - exercised in packaged runtime, not training tests
        raise RuntimeError(
            "Training with tuning enabled requires the optional 'train' dependencies. "
            "Run `pdm install -G train` before invoking the training pipeline."
        ) from exc

    tuning_frame, tuning_labels, tuning_weights = _sample_for_tuning(
        x_train,
        y_train,
        sample_weight=sample_weight,
        spec=spec,
    )
    tuning_folds = _safe_cv_folds(tuning_labels, requested_folds=spec.tuning_cv_folds)
    if tuning_folds < 2:
        return {}

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    sampler = optuna.samplers.TPESampler(seed=spec.random_state)
    study = optuna.create_study(direction="maximize", sampler=sampler)

    def objective(trial: Trial) -> float:
        params = {
            "max_depth": trial.suggest_int(
                "max_depth",
                int(spec.search_space["max_depth"]["low"]),
                int(spec.search_space["max_depth"]["high"]),
            ),
            "min_samples_split": trial.suggest_int(
                "min_samples_split",
                int(spec.search_space["min_samples_split"]["low"]),
                int(spec.search_space["min_samples_split"]["high"]),
            ),
            "min_samples_leaf": trial.suggest_int(
                "min_samples_leaf",
                int(spec.search_space["min_samples_leaf"]["low"]),
                int(spec.search_space["min_samples_leaf"]["high"]),
            ),
            "max_leaf_nodes": trial.suggest_int(
                "max_leaf_nodes",
                int(spec.search_space["max_leaf_nodes"]["low"]),
                int(spec.search_space["max_leaf_nodes"]["high"]),
            ),
            "ccp_alpha": trial.suggest_float(
                "ccp_alpha",
                float(spec.search_space["ccp_alpha"]["low"]),
                float(spec.search_space["ccp_alpha"]["high"]),
                log=True,
            ),
        }
        scores: list[float] = []
        splitter = StratifiedKFold(
            n_splits=tuning_folds,
            shuffle=True,
            random_state=spec.random_state,
        )
        for train_idx, valid_idx in splitter.split(tuning_frame, tuning_labels):
            fold_train = tuning_frame.iloc[train_idx]
            fold_valid = tuning_frame.iloc[valid_idx]
            fold_y_train = tuning_labels.iloc[train_idx]
            fold_y_valid = tuning_labels.iloc[valid_idx]
            fold_weights = (
                tuning_weights.iloc[train_idx].reset_index(drop=True)
                if tuning_weights is not None
                else None
            )
            fold_valid_weights = (
                tuning_weights.iloc[valid_idx].reset_index(drop=True)
                if tuning_weights is not None
                else None
            )
            pipeline = _make_training_pipeline(feature_names, spec=spec, overrides=params)
            pipeline.fit(fold_train, fold_y_train, sample_weight=fold_weights)
            probabilities = _predict_positive_class(pipeline, fold_valid)
            metric_value = _score_tuning_metric(
                y_true=fold_y_valid,
                probabilities=probabilities,
                metric_name=spec.tuning_metric,
                sample_weight=fold_valid_weights,
            )
            scores.append(metric_value)
        return float(np.mean(scores))

    study.optimize(
        objective,
        n_trials=spec.tuning_n_trials,
        timeout=spec.tuning_timeout_seconds,
        show_progress_bar=False,
    )
    return dict(study.best_params)


def _sample_for_tuning(
    x_train: pd.DataFrame,
    y_train: pd.Series,
    *,
    sample_weight: pd.Series | None,
    spec: TrainingSpec,
) -> tuple[pd.DataFrame, pd.Series, pd.Series | None]:
    if spec.tuning_sample_size is None or len(x_train) <= spec.tuning_sample_size:
        return x_train, y_train, sample_weight
    split_values = train_test_split(
        x_train,
        y_train,
        sample_weight if sample_weight is not None else pd.Series(1.0, index=y_train.index),
        train_size=spec.tuning_sample_size,
        random_state=spec.random_state,
        stratify=y_train,
    )
    sampled_x, _, sampled_y, _, sampled_weights, _ = split_values
    return (
        sampled_x.reset_index(drop=True),
        sampled_y.reset_index(drop=True),
        sampled_weights.reset_index(drop=True) if sample_weight is not None else None,
    )


def _score_tuning_metric(
    *,
    y_true: pd.Series,
    probabilities: np.ndarray,
    metric_name: str,
    sample_weight: pd.Series | None,
) -> float:
    if metric_name == "roc_auc":
        return float(roc_auc_score(y_true, probabilities, sample_weight=sample_weight))
    return float(average_precision_score(y_true, probabilities, sample_weight=sample_weight))


def _predict_positive_class(
    model: CalibratedClassifierCV | Pipeline,
    features: pd.DataFrame,
) -> np.ndarray:
    probabilities = model.predict_proba(features)
    classes = np.asarray(model.classes_)  # type: ignore[attr-defined]
    matches = np.where(classes == 1)[0]
    if len(matches) != 1:
        raise ValueError(
            f"Model classes_ must contain exactly one positive label 1 (got {classes})."
        )
    return np.asarray(probabilities)[:, int(matches[0])]


def _binary_metrics(
    y_true: pd.Series,
    probabilities: np.ndarray,
    *,
    sample_weight: pd.Series | None = None,
) -> dict[str, float | None]:
    metrics: dict[str, float | None] = {
        "average_precision": None,
        "roc_auc": None,
        "brier_score": None,
    }
    if len(np.unique(y_true)) < 2:
        return metrics
    metrics["average_precision"] = float(
        average_precision_score(y_true, probabilities, sample_weight=sample_weight)
    )
    metrics["roc_auc"] = float(roc_auc_score(y_true, probabilities, sample_weight=sample_weight))
    metrics["brier_score"] = float(
        brier_score_loss(y_true, probabilities, sample_weight=sample_weight)
    )
    return metrics


def _feature_importances(pipeline: Pipeline) -> list[dict[str, float | str]]:
    model = pipeline.named_steps["model"]
    importances = getattr(model, "feature_importances_", None)
    if importances is None:
        return []
    rows = [
        {
            "feature": feature_name,
            "label": FEATURE_LABELS.get(feature_name, feature_name),
            "importance": float(importance),
        }
        for feature_name, importance in zip(
            pipeline.named_steps["preprocess"].get_feature_names_out(),
            importances,
            strict=True,
        )
    ]
    rows.sort(key=lambda item: float(item["importance"]), reverse=True)
    return rows


def _build_dataset_info(spec: TrainingSpec, *, dataset_path: Path) -> DatasetInfo:
    paths = build_ingest_paths(spec.base_data_dir)
    provenance_path = paths.provenance_integrated_person_year(spec.year)
    if dataset_path == paths.integrated_person_year_parquet(spec.year) and provenance_path.exists():
        payload = json.loads(provenance_path.read_text(encoding="utf-8"))
        retrieved_at = payload.get("retrieved_at")
        return DatasetInfo(
            name=str(payload.get("dataset_name", "integrated_person_year")),
            version=str(payload.get("dataset_version", spec.year)),
            retrieved_at=(
                dt.datetime.fromisoformat(retrieved_at) if isinstance(retrieved_at, str) else None
            ),
            sources=[str(item) for item in payload.get("sources", [])],
        )
    return DatasetInfo(
        name=dataset_path.stem,
        version=str(spec.year),
        sources=[],
    )


def _safe_cv_folds(labels: pd.Series, *, requested_folds: int) -> int:
    counts = labels.value_counts()
    if len(counts) < 2:
        return 0
    min_class_count = int(counts.min())
    if min_class_count < 2:
        return 0
    return min(requested_folds, min_class_count)


def _validate_binary_target(labels: pd.Series, *, condition_id: str) -> None:
    values = set(labels.astype(int).unique().tolist())
    if values != {0, 1}:
        raise ValueError(
            f"Condition {condition_id} must be binary after dropping nulls (got {sorted(values)})."
        )


def _detect_git_commit() -> str | None:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
