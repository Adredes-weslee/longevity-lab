"""Transparent estimators and diagnostics for causal workbench reports."""

from __future__ import annotations

from typing import Any

import numpy as np  # type: ignore[import-untyped]
import pandas as pd  # type: ignore[import-untyped]
from sklearn.linear_model import LogisticRegression  # type: ignore[import-untyped]

from longevity_lab.causal.datasets import CausalWorkbenchConfig, PreparedCausalDataset


def run_adjustment_diagnostics(
    prepared: PreparedCausalDataset,
    config: CausalWorkbenchConfig,
) -> dict[str, Any]:
    """Compute missingness, covariate balance, and propensity-overlap diagnostics."""
    frame = prepared.frame
    propensities = _fit_propensity_scores(frame, config)
    return {
        "missingness": prepared.missingness,
        "weight_imputation": prepared.weight_imputation,
        "propensity_overlap": _propensity_overlap(frame, propensities, config),
        "top_standardized_mean_differences": _standardized_mean_differences(frame, config),
    }


def estimate_smoking_lung_effect(
    prepared: PreparedCausalDataset,
    config: CausalWorkbenchConfig,
) -> dict[str, Any]:
    """Estimate the smoking association/effect and local refutation checks."""
    return estimate_causal_effect(prepared, config)


def estimate_causal_effect(
    prepared: PreparedCausalDataset,
    config: CausalWorkbenchConfig,
) -> dict[str, Any]:
    """Estimate a configured causal contrast with diagnostics and local refutations."""
    frame = prepared.frame
    try:
        propensities = _fit_propensity_scores(frame, config)
    except ValueError as exc:
        diagnostics = _failed_diagnostics(
            prepared=prepared,
            reason=str(exc),
        )
        return {
            "estimate": None,
            "diagnostics": diagnostics,
            "refutations": _not_run_refutations(
                status="failed_diagnostic",
                reason=str(exc),
            ),
        }

    overlap = _propensity_overlap(frame, propensities, config)
    smd = _standardized_mean_differences(frame, config)
    gate = _diagnostic_gate(overlap, smd, config)
    diagnostics = {
        "missingness": prepared.missingness,
        "weight_imputation": prepared.weight_imputation,
        "diagnostic_gate": gate,
        "propensity_overlap": overlap,
        "top_standardized_mean_differences": smd,
    }
    if gate["status"] == "failed":
        return {
            "estimate": None,
            "diagnostics": diagnostics,
            "refutations": _not_run_refutations(
                status="failed_diagnostic",
                reason="; ".join(str(item) for item in gate["warnings"]),
            ),
        }

    try:
        primary = _estimate_effect_core(frame, config)
    except ValueError as exc:
        diagnostics["diagnostic_gate"] = {
            **gate,
            "status": "failed",
            "warnings": [*gate["warnings"], str(exc)],
        }
        return {
            "estimate": None,
            "diagnostics": diagnostics,
            "refutations": _not_run_refutations(
                status="failed_diagnostic",
                reason=str(exc),
            ),
        }

    return {
        "estimate": primary,
        "diagnostics": diagnostics,
        "refutations": _run_refutations(
            frame=frame,
            config=config,
            primary_risk_difference=float(primary["risk_difference"]),
            propensities=propensities,
        ),
    }


def run_effect_diagnostics_for_frame(
    frame: pd.DataFrame,
    config: CausalWorkbenchConfig,
) -> dict[str, Any]:
    """Compute diagnostic gate inputs for one analysis frame."""
    propensities = _fit_propensity_scores(frame, config)
    overlap = _propensity_overlap(frame, propensities, config)
    smd = _standardized_mean_differences(frame, config)
    return {
        "diagnostic_gate": _diagnostic_gate(overlap, smd, config),
        "propensity_overlap": overlap,
        "top_standardized_mean_differences": smd,
    }


def estimate_effect_for_frame(
    frame: pd.DataFrame,
    config: CausalWorkbenchConfig,
    *,
    adjustment_columns: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """Estimate the configured g-computation contrast for one analysis frame."""
    return _estimate_effect_core(frame, config, adjustment_columns=adjustment_columns)


def _diagnostic_gate(
    overlap: dict[str, Any],
    smd: list[dict[str, float | str]],
    config: CausalWorkbenchConfig,
) -> dict[str, Any]:
    """Return pass/warning/fail status for diagnostics checked before estimation."""
    warnings: list[str] = []
    total_rows = int(overlap["treated_rows"]) + int(overlap["control_rows"])
    inside_overlap = int(overlap["rows_inside_configured_overlap"])
    if int(overlap["treated_rows"]) == 0 or int(overlap["control_rows"]) == 0:
        return {"status": "failed", "warnings": ["Treatment or control group is empty."]}
    if inside_overlap == 0:
        return {"status": "failed", "warnings": ["No rows inside configured propensity overlap."]}
    if int(overlap["rows_below_min_propensity"]) > 0:
        warnings.append(
            f"{overlap['rows_below_min_propensity']} rows below min propensity "
            f"{config.min_propensity}."
        )
    if int(overlap["rows_above_max_propensity"]) > 0:
        warnings.append(
            f"{overlap['rows_above_max_propensity']} rows above max propensity "
            f"{config.max_propensity}."
        )
    top_smd = float(smd[0]["abs_standardized_mean_difference"]) if smd else 0.0
    if top_smd > config.max_abs_smd_warning:
        warnings.append(
            f"Top absolute standardized mean difference {top_smd:.3f} exceeds "
            f"{config.max_abs_smd_warning}."
        )
    status = "warning" if warnings else "passed"
    return {
        "status": status,
        "warnings": warnings,
        "rows_inside_configured_overlap": inside_overlap,
        "total_rows": total_rows,
        "min_propensity": config.min_propensity,
        "max_propensity": config.max_propensity,
        "max_abs_smd_warning": config.max_abs_smd_warning,
    }


def _failed_diagnostics(
    *,
    prepared: PreparedCausalDataset,
    reason: str,
) -> dict[str, Any]:
    return {
        "missingness": prepared.missingness,
        "weight_imputation": prepared.weight_imputation,
        "diagnostic_gate": {
            "status": "failed",
            "warnings": [reason],
            "rows_inside_configured_overlap": 0,
            "total_rows": prepared.analysis_rows,
        },
        "propensity_overlap": None,
        "top_standardized_mean_differences": [],
    }


def _not_run_refutations(*, status: str, reason: str) -> list[dict[str, Any]]:
    return [
        {
            "name": name,
            "status": status,
            "note": f"Not run because prerequisite diagnostics failed: {reason}",
            "rows": 0,
        }
        for name in (
            "permuted_treatment_placebo",
            "subset_refit",
            "random_common_cause",
            "overlap_trimmed_refit",
        )
    ]


def _estimate_effect_core(
    frame: pd.DataFrame,
    config: CausalWorkbenchConfig,
    *,
    adjustment_columns: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    adjustment = adjustment_columns or config.adjustment_columns
    treatment = frame[config.treatment_column].astype(int)
    outcome = frame[config.outcome_column].astype(int)
    weights = frame[config.sample_weight_column].astype("float64")
    _require_two_classes(treatment, "treatment")
    _require_two_classes(outcome, "outcome")

    crude_treated = _weighted_mean(outcome.loc[treatment == 1], weights.loc[treatment == 1])
    crude_control = _weighted_mean(outcome.loc[treatment == 0], weights.loc[treatment == 0])

    x_train = _encoded_features(
        frame,
        columns=(config.treatment_column, *adjustment),
        categorical_columns=config.categorical_columns,
    )
    model = _logistic_model(config)
    model.fit(x_train, outcome, sample_weight=weights)

    treated_frame = frame.copy()
    control_frame = frame.copy()
    treated_frame[config.treatment_column] = 1
    control_frame[config.treatment_column] = 0
    x_treated = _align_columns(
        _encoded_features(
            treated_frame,
            columns=(config.treatment_column, *adjustment),
            categorical_columns=config.categorical_columns,
        ),
        reference_columns=tuple(x_train.columns),
    )
    x_control = _align_columns(
        _encoded_features(
            control_frame,
            columns=(config.treatment_column, *adjustment),
            categorical_columns=config.categorical_columns,
        ),
        reference_columns=tuple(x_train.columns),
    )
    treated_risk = _weighted_mean(
        pd.Series(_positive_probabilities(model, x_treated)),
        weights.reset_index(drop=True),
    )
    control_risk = _weighted_mean(
        pd.Series(_positive_probabilities(model, x_control)),
        weights.reset_index(drop=True),
    )
    risk_difference = treated_risk - control_risk
    return {
        "method": "weighted_logistic_g_computation",
        "estimand": config.estimand,
        "rows": int(len(frame)),
        "weighted_rows": float(weights.sum()),
        "treated_rows": int((treatment == 1).sum()),
        "control_rows": int((treatment == 0).sum()),
        "crude_treated_risk": crude_treated,
        "crude_control_risk": crude_control,
        "crude_risk_difference": crude_treated - crude_control,
        "adjusted_treated_risk": treated_risk,
        "adjusted_control_risk": control_risk,
        "risk_difference": risk_difference,
        "risk_ratio": _ratio(treated_risk, control_risk),
        "odds_ratio": _odds_ratio(treated_risk, control_risk),
        "model": {
            "family": "logistic_regression",
            "adjustment_columns": list(adjustment),
            "categorical_columns": list(config.categorical_columns),
        },
    }


def _run_refutations(
    *,
    frame: pd.DataFrame,
    config: CausalWorkbenchConfig,
    primary_risk_difference: float,
    propensities: np.ndarray,
) -> list[dict[str, Any]]:
    refutations = [
        _permuted_treatment_refutation(frame, config, primary_risk_difference),
        _subset_refutation(frame, config, primary_risk_difference),
        _random_common_cause_refutation(frame, config, primary_risk_difference),
        _overlap_trimmed_refutation(frame, config, primary_risk_difference, propensities),
    ]
    return refutations


def _permuted_treatment_refutation(
    frame: pd.DataFrame,
    config: CausalWorkbenchConfig,
    primary_risk_difference: float,
) -> dict[str, Any]:
    rng = np.random.default_rng(config.random_state)
    placebo = frame.copy()
    placebo[config.treatment_column] = rng.permutation(placebo[config.treatment_column].to_numpy())
    return _safe_refit(
        name="permuted_treatment_placebo",
        frame=placebo,
        config=config,
        primary_risk_difference=primary_risk_difference,
        note="Negative-control exposure: treatment permuted with a fixed seed.",
    )


def _subset_refutation(
    frame: pd.DataFrame,
    config: CausalWorkbenchConfig,
    primary_risk_difference: float,
) -> dict[str, Any]:
    subset = frame.sample(frac=0.8, random_state=config.random_state).reset_index(drop=True)
    return _safe_refit(
        name="subset_refit",
        frame=subset,
        config=config,
        primary_risk_difference=primary_risk_difference,
        note="Subset refutation using 80 percent of rows.",
    )


def _random_common_cause_refutation(
    frame: pd.DataFrame,
    config: CausalWorkbenchConfig,
    primary_risk_difference: float,
) -> dict[str, Any]:
    rng = np.random.default_rng(config.random_state)
    augmented = frame.copy()
    augmented["random_common_cause_noise"] = rng.normal(size=len(augmented))
    adjustment = (*config.adjustment_columns, "random_common_cause_noise")
    return _safe_refit(
        name="random_common_cause",
        frame=augmented,
        config=config,
        primary_risk_difference=primary_risk_difference,
        note="Random common-cause refutation using deterministic Gaussian noise.",
        adjustment_columns=adjustment,
    )


def _overlap_trimmed_refutation(
    frame: pd.DataFrame,
    config: CausalWorkbenchConfig,
    primary_risk_difference: float,
    propensities: np.ndarray,
) -> dict[str, Any]:
    keep = (propensities >= config.trim_min_propensity) & (
        propensities <= config.trim_max_propensity
    )
    trimmed = frame.loc[keep].reset_index(drop=True)
    if len(trimmed) < 10:
        return {
            "name": "overlap_trimmed_refit",
            "status": "skipped",
            "note": "Too few rows remained after propensity trimming.",
            "rows": int(len(trimmed)),
        }
    return _safe_refit(
        name="overlap_trimmed_refit",
        frame=trimmed,
        config=config,
        primary_risk_difference=primary_risk_difference,
        note=(
            "Refit after keeping rows within configured propensity trim bounds "
            f"[{config.trim_min_propensity}, {config.trim_max_propensity}]."
        ),
    )


def _safe_refit(
    *,
    name: str,
    frame: pd.DataFrame,
    config: CausalWorkbenchConfig,
    primary_risk_difference: float,
    note: str,
    adjustment_columns: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    try:
        estimate = _estimate_effect_core(frame, config, adjustment_columns=adjustment_columns)
    except ValueError as exc:
        return {"name": name, "status": "skipped", "note": f"{note} {exc}", "rows": len(frame)}
    risk_difference = float(estimate["risk_difference"])
    return {
        "name": name,
        "status": "ok",
        "note": note,
        "rows": int(len(frame)),
        "risk_difference": risk_difference,
        "difference_from_primary": risk_difference - primary_risk_difference,
    }


def _fit_propensity_scores(frame: pd.DataFrame, config: CausalWorkbenchConfig) -> np.ndarray:
    treatment = frame[config.treatment_column].astype(int)
    _require_two_classes(treatment, "treatment")
    weights = frame[config.sample_weight_column].astype("float64")
    x_train = _encoded_features(
        frame,
        columns=config.adjustment_columns,
        categorical_columns=config.categorical_columns,
    )
    model = _logistic_model(config)
    model.fit(x_train, treatment, sample_weight=weights)
    return _positive_probabilities(model, x_train)


def _propensity_overlap(
    frame: pd.DataFrame,
    propensities: np.ndarray,
    config: CausalWorkbenchConfig,
) -> dict[str, Any]:
    treatment = frame[config.treatment_column].astype(int).to_numpy()
    treated_prop = propensities[treatment == 1]
    control_prop = propensities[treatment == 0]
    return {
        "treated_rows": int((treatment == 1).sum()),
        "control_rows": int((treatment == 0).sum()),
        "min": float(np.min(propensities)),
        "p05": float(np.quantile(propensities, 0.05)),
        "median": float(np.median(propensities)),
        "p95": float(np.quantile(propensities, 0.95)),
        "max": float(np.max(propensities)),
        "treated_range": [float(np.min(treated_prop)), float(np.max(treated_prop))],
        "control_range": [float(np.min(control_prop)), float(np.max(control_prop))],
        "rows_below_min_propensity": int((propensities < config.min_propensity).sum()),
        "rows_above_max_propensity": int((propensities > config.max_propensity).sum()),
        "rows_inside_configured_overlap": int(
            (
                (propensities >= config.min_propensity) & (propensities <= config.max_propensity)
            ).sum()
        ),
    }


def _standardized_mean_differences(
    frame: pd.DataFrame,
    config: CausalWorkbenchConfig,
) -> list[dict[str, float | str]]:
    encoded = _encoded_features(
        frame,
        columns=config.adjustment_columns,
        categorical_columns=config.categorical_columns,
    )
    treatment = frame[config.treatment_column].astype(int).reset_index(drop=True)
    weights = frame[config.sample_weight_column].astype("float64").reset_index(drop=True)
    rows: list[dict[str, float | str]] = []
    for column in encoded.columns:
        values = encoded[column].reset_index(drop=True)
        treated_values = values.loc[treatment == 1]
        control_values = values.loc[treatment == 0]
        treated_weights = weights.loc[treatment == 1]
        control_weights = weights.loc[treatment == 0]
        treated_mean = _weighted_mean(treated_values, treated_weights)
        control_mean = _weighted_mean(control_values, control_weights)
        treated_var = _weighted_variance(treated_values, treated_weights, treated_mean)
        control_var = _weighted_variance(control_values, control_weights, control_mean)
        pooled_sd = float(np.sqrt(max((treated_var + control_var) / 2.0, 0.0)))
        smd = 0.0 if pooled_sd == 0 else (treated_mean - control_mean) / pooled_sd
        rows.append(
            {
                "feature": str(column),
                "standardized_mean_difference": float(smd),
                "abs_standardized_mean_difference": float(abs(smd)),
            }
        )
    rows.sort(key=lambda item: float(item["abs_standardized_mean_difference"]), reverse=True)
    return rows[:10]


def _encoded_features(
    frame: pd.DataFrame,
    *,
    columns: tuple[str, ...],
    categorical_columns: tuple[str, ...],
) -> pd.DataFrame:
    parts: list[pd.DataFrame] = []
    categorical_set = set(categorical_columns)
    for column in columns:
        if column in categorical_set:
            values = frame[column].astype("string").fillna("missing")
            parts.append(pd.get_dummies(values, prefix=column, dtype="float64"))
            continue
        numeric = pd.to_numeric(frame[column], errors="coerce").astype("float64")
        non_null = numeric.dropna()
        fill_value = float(non_null.median()) if not non_null.empty else 0.0
        parts.append(pd.DataFrame({column: numeric.fillna(fill_value).astype("float64")}))
    if not parts:
        return pd.DataFrame(index=frame.index)
    return pd.concat(parts, axis=1).reset_index(drop=True)


def _align_columns(frame: pd.DataFrame, *, reference_columns: tuple[str, ...]) -> pd.DataFrame:
    return frame.reindex(columns=list(reference_columns), fill_value=0.0)


def _logistic_model(config: CausalWorkbenchConfig) -> LogisticRegression:
    return LogisticRegression(
        max_iter=2_000,
        random_state=config.random_state,
        solver="liblinear",
    )


def _positive_probabilities(model: LogisticRegression, features: pd.DataFrame) -> np.ndarray:
    probabilities = model.predict_proba(features)
    classes = np.asarray(model.classes_)
    matches = np.where(classes == 1)[0]
    if len(matches) != 1:
        raise ValueError("Fitted logistic model does not contain positive class 1.")
    return np.asarray(probabilities)[:, int(matches[0])]


def _weighted_mean(values: pd.Series, weights: pd.Series) -> float:
    numeric = pd.to_numeric(values, errors="coerce").astype("float64")
    numeric_weights = pd.to_numeric(weights, errors="coerce").astype("float64")
    valid = numeric.notna() & numeric_weights.notna() & (numeric_weights > 0)
    if not bool(valid.any()):
        return float(numeric.mean())
    return float(np.average(numeric.loc[valid], weights=numeric_weights.loc[valid]))


def _weighted_variance(values: pd.Series, weights: pd.Series, mean: float) -> float:
    numeric = pd.to_numeric(values, errors="coerce").astype("float64")
    numeric_weights = pd.to_numeric(weights, errors="coerce").astype("float64")
    valid = numeric.notna() & numeric_weights.notna() & (numeric_weights > 0)
    if not bool(valid.any()):
        return 0.0
    centered = numeric.loc[valid] - mean
    return float(np.average(centered * centered, weights=numeric_weights.loc[valid]))


def _ratio(numerator: float, denominator: float) -> float | None:
    if denominator <= 0:
        return None
    return numerator / denominator


def _odds_ratio(treated_risk: float, control_risk: float) -> float | None:
    eps = 1e-9
    if treated_risk >= 1.0 or control_risk >= 1.0:
        return None
    treated_odds = max(treated_risk, eps) / max(1.0 - treated_risk, eps)
    control_odds = max(control_risk, eps) / max(1.0 - control_risk, eps)
    return treated_odds / control_odds


def _require_two_classes(series: pd.Series, label: str) -> None:
    values = set(series.astype(int).unique().tolist())
    if values != {0, 1}:
        raise ValueError(f"Causal {label} requires both 0 and 1 classes; got {sorted(values)}.")
