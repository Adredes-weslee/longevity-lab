"""Subgroup and optional heterogeneous-effect reporting for causal workbench runs."""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from typing import Any

import numpy as np  # type: ignore[import-untyped]
import pandas as pd  # type: ignore[import-untyped]

from longevity_lab.causal.datasets import CausalWorkbenchConfig, PreparedCausalDataset
from longevity_lab.causal.estimators import (
    estimate_effect_for_frame,
    run_effect_diagnostics_for_frame,
)

MIN_SUBGROUP_CELL_SIZE = 25
MIN_SUBGROUP_TOTAL_ROWS = 50
MIN_OVERLAP_ROWS = 50
MIN_CAUSAL_FOREST_ROWS = 200
MAX_CAUSAL_FOREST_ROWS = 5_000
MAX_CONTEXT_STRATA = 6

_DEFAULT_CATEGORICAL_STRATA: tuple[tuple[str, str], ...] = (
    ("sex", "sex"),
    ("race_ethnicity", "race_ethnicity"),
    ("state_fips", "state_fips"),
    ("survey_year", "year"),
)


@dataclass(frozen=True, slots=True)
class _Stratum:
    name: str
    source_column: str
    kind: str
    values: pd.Series


def run_heterogeneity_analysis(
    prepared: PreparedCausalDataset,
    config: CausalWorkbenchConfig,
    *,
    min_cell_size: int = MIN_SUBGROUP_CELL_SIZE,
    min_total_rows: int = MIN_SUBGROUP_TOTAL_ROWS,
    min_overlap_rows: int = MIN_OVERLAP_ROWS,
) -> dict[str, Any]:
    """Estimate subgroup effects when conservative diagnostics pass."""
    frame = prepared.frame
    strata = _candidate_strata(frame)
    candidate_records: list[dict[str, Any]] = []
    subgroup_records: list[dict[str, Any]] = []
    warnings: list[str] = []

    for stratum in strata:
        levels = _observed_levels(stratum.values)
        if len(levels) < 2:
            record = {
                "name": stratum.name,
                "source_column": stratum.source_column,
                "kind": stratum.kind,
                "status": "skipped",
                "reason": "Fewer than two observed strata levels are available.",
                "levels": len(levels),
            }
            candidate_records.append(record)
            warnings.append(f"{stratum.name}: fewer than two observed levels.")
            continue

        candidate_start = len(subgroup_records)
        for level in levels:
            mask = _level_mask(stratum.values, level)
            subgroup = frame.loc[mask].reset_index(drop=True)
            subgroup_records.append(
                _estimate_subgroup(
                    subgroup=subgroup,
                    config=config,
                    stratum=stratum,
                    level=level,
                    min_cell_size=min_cell_size,
                    min_total_rows=min_total_rows,
                    min_overlap_rows=min_overlap_rows,
                )
            )

        candidate_subgroups = subgroup_records[candidate_start:]
        estimated = sum(1 for item in candidate_subgroups if item["status"] == "ok")
        skipped = len(candidate_subgroups) - estimated
        candidate_records.append(
            {
                "name": stratum.name,
                "source_column": stratum.source_column,
                "kind": stratum.kind,
                "status": "ok" if estimated else "skipped",
                "levels": len(levels),
                "estimated_subgroups": estimated,
                "skipped_subgroups": skipped,
            }
        )
        if skipped:
            warnings.append(
                f"{stratum.name}: {skipped} subgroup level(s) skipped by cell-size or overlap "
                "diagnostics."
            )

    reportable = sum(1 for item in subgroup_records if item["status"] == "ok")
    status = "estimated" if reportable else "no_reportable_subgroups"
    if not strata:
        warnings.append("No supported subgroup or context strata columns were available.")

    return {
        "status": status,
        "policy": {
            "method": "within_subgroup_weighted_logistic_g_computation",
            "min_cell_size_per_treatment_arm": min_cell_size,
            "min_total_rows": min_total_rows,
            "min_rows_inside_configured_overlap": min_overlap_rows,
            "required_overlap_bounds": [config.min_propensity, config.max_propensity],
            "effect_scale": "risk_difference",
        },
        "candidate_strata": candidate_records,
        "subgroups": subgroup_records,
        "optional_methods": _optional_method_records(prepared=prepared, config=config),
        "warnings": warnings,
    }


def build_heterogeneity_not_run(reason: str) -> dict[str, Any]:
    """Build an explicit heterogeneity payload for failed prerequisite runs."""
    return {
        "status": "failed_diagnostic",
        "policy": {
            "method": "within_subgroup_weighted_logistic_g_computation",
            "min_cell_size_per_treatment_arm": MIN_SUBGROUP_CELL_SIZE,
            "min_total_rows": MIN_SUBGROUP_TOTAL_ROWS,
            "min_rows_inside_configured_overlap": MIN_OVERLAP_ROWS,
            "effect_scale": "risk_difference",
        },
        "candidate_strata": [],
        "subgroups": [],
        "optional_methods": [
            {
                "name": "causal_forest_dml",
                "status": "skipped",
                "dependency": "econml",
                "reason": f"Not run because primary causal prerequisites failed: {reason}",
            },
            {
                "name": "dowhy_heterogeneity_refuters",
                "status": "skipped",
                "dependency": "dowhy",
                "reason": f"Not run because primary causal prerequisites failed: {reason}",
            },
        ],
        "warnings": [reason],
    }


def _candidate_strata(frame: pd.DataFrame) -> list[_Stratum]:
    strata: list[_Stratum] = []
    if "age" in frame.columns:
        strata.append(
            _Stratum(
                name="age_band",
                source_column="age",
                kind="derived_fixed_band",
                values=_age_band(frame["age"]),
            )
        )
    for name, column in _DEFAULT_CATEGORICAL_STRATA:
        if column not in frame.columns:
            continue
        strata.append(
            _Stratum(
                name=name,
                source_column=column,
                kind="categorical",
                values=frame[column],
            )
        )
    if "annual_aqi" in frame.columns:
        strata.append(
            _Stratum(
                name="annual_aqi_band",
                source_column="annual_aqi",
                kind="derived_context_band",
                values=_annual_aqi_band(frame["annual_aqi"]),
            )
        )

    context_columns = [
        column
        for column in sorted(frame.columns)
        if _is_context_column(column) and column != "annual_aqi"
    ][:MAX_CONTEXT_STRATA]
    for column in context_columns:
        strata.append(
            _Stratum(
                name=f"{column}_band",
                source_column=column,
                kind="derived_context_quantile_band",
                values=_numeric_quantile_band(frame[column]),
            )
        )
    return strata


def _estimate_subgroup(
    *,
    subgroup: pd.DataFrame,
    config: CausalWorkbenchConfig,
    stratum: _Stratum,
    level: str,
    min_cell_size: int,
    min_total_rows: int,
    min_overlap_rows: int,
) -> dict[str, Any]:
    treatment = subgroup[config.treatment_column].astype(int)
    outcome = subgroup[config.outcome_column].astype(int)
    treated_rows = int((treatment == 1).sum())
    control_rows = int((treatment == 0).sum())
    base_record: dict[str, Any] = {
        "stratum": stratum.name,
        "source_column": stratum.source_column,
        "level": level,
        "rows": int(len(subgroup)),
        "treated_rows": treated_rows,
        "control_rows": control_rows,
        "estimate": None,
        "diagnostics": None,
        "warnings": [],
    }
    warnings = _cell_size_warnings(
        rows=len(subgroup),
        treated_rows=treated_rows,
        control_rows=control_rows,
        min_cell_size=min_cell_size,
        min_total_rows=min_total_rows,
    )
    if len(set(outcome.tolist())) != 2:
        warnings.append("Subgroup outcome does not contain both 0 and 1 classes.")
    if warnings:
        return {
            **base_record,
            "status": "skipped",
            "reason": "; ".join(warnings),
            "warnings": warnings,
        }

    try:
        diagnostics = run_effect_diagnostics_for_frame(subgroup, config)
    except ValueError as exc:
        return {
            **base_record,
            "status": "skipped",
            "reason": str(exc),
            "warnings": [str(exc)],
        }

    overlap = diagnostics["propensity_overlap"]
    overlap_warnings = _overlap_warnings(
        overlap=overlap,
        diagnostics=diagnostics,
        min_overlap_rows=min_overlap_rows,
    )
    if overlap_warnings:
        return {
            **base_record,
            "status": "skipped",
            "reason": "; ".join(overlap_warnings),
            "diagnostics": diagnostics,
            "warnings": overlap_warnings,
        }

    try:
        estimate = estimate_effect_for_frame(subgroup, config)
    except ValueError as exc:
        return {
            **base_record,
            "status": "skipped",
            "reason": str(exc),
            "diagnostics": diagnostics,
            "warnings": [str(exc)],
        }

    diagnostic_warnings = [str(item) for item in diagnostics["diagnostic_gate"].get("warnings", [])]
    return {
        **base_record,
        "status": "ok",
        "reason": "Diagnostics passed with reportable subgroup cell sizes.",
        "estimate": estimate,
        "diagnostics": diagnostics,
        "warnings": diagnostic_warnings,
    }


def _cell_size_warnings(
    *,
    rows: int,
    treated_rows: int,
    control_rows: int,
    min_cell_size: int,
    min_total_rows: int,
) -> list[str]:
    warnings: list[str] = []
    if rows < min_total_rows:
        warnings.append(f"Rows {rows} below minimum total {min_total_rows}.")
    if treated_rows < min_cell_size:
        warnings.append(f"Treated rows {treated_rows} below minimum cell size {min_cell_size}.")
    if control_rows < min_cell_size:
        warnings.append(f"Control rows {control_rows} below minimum cell size {min_cell_size}.")
    return warnings


def _overlap_warnings(
    *,
    overlap: dict[str, Any],
    diagnostics: dict[str, Any],
    min_overlap_rows: int,
) -> list[str]:
    warnings: list[str] = []
    gate = diagnostics["diagnostic_gate"]
    if gate["status"] == "failed":
        warnings.extend(str(item) for item in gate.get("warnings", []))
    rows_inside = int(overlap["rows_inside_configured_overlap"])
    if rows_inside < min_overlap_rows:
        warnings.append(
            f"Rows inside configured overlap {rows_inside} below minimum {min_overlap_rows}."
        )
    treated_range = overlap["treated_range"]
    control_range = overlap["control_range"]
    lower = max(float(treated_range[0]), float(control_range[0]))
    upper = min(float(treated_range[1]), float(control_range[1]))
    if lower >= upper:
        warnings.append("Treated and control propensity ranges do not share common support.")
    return warnings


def _optional_method_records(
    *,
    prepared: PreparedCausalDataset,
    config: CausalWorkbenchConfig,
) -> list[dict[str, Any]]:
    return [
        _causal_forest_dml_record(prepared=prepared, config=config),
        _dowhy_heterogeneity_refuters_record(),
    ]


def _causal_forest_dml_record(
    *,
    prepared: PreparedCausalDataset,
    config: CausalWorkbenchConfig,
) -> dict[str, Any]:
    if not _has_optional_dependency("econml"):
        return {
            "name": "causal_forest_dml",
            "status": "skipped",
            "dependency": "econml",
            "reason": "Optional dependency `econml` is not installed in the default environment.",
        }
    frame = prepared.frame
    if len(frame) < MIN_CAUSAL_FOREST_ROWS:
        return {
            "name": "causal_forest_dml",
            "status": "skipped",
            "dependency": "econml",
            "reason": (
                f"Requires at least {MIN_CAUSAL_FOREST_ROWS} rows for a conservative "
                f"CausalForestDML screen; got {len(frame)}."
            ),
            "rows": int(len(frame)),
        }
    try:
        return _fit_causal_forest_dml(frame=frame, config=config)
    except Exception as exc:  # pragma: no cover - only active with optional dependency.
        return {
            "name": "causal_forest_dml",
            "status": "skipped",
            "dependency": "econml",
            "reason": f"CausalForestDML was available but did not complete: {exc}",
            "rows": int(len(frame)),
        }


def _fit_causal_forest_dml(
    *,
    frame: pd.DataFrame,
    config: CausalWorkbenchConfig,
) -> dict[str, Any]:
    from econml.dml import CausalForestDML  # type: ignore[import-not-found,import-untyped]
    from sklearn.ensemble import (  # type: ignore[import-untyped]
        RandomForestClassifier,
        RandomForestRegressor,
    )

    working = (
        frame.sample(n=MAX_CAUSAL_FOREST_ROWS, random_state=config.random_state)
        if len(frame) > MAX_CAUSAL_FOREST_ROWS
        else frame
    ).reset_index(drop=True)
    features = pd.get_dummies(
        working.loc[:, list(config.adjustment_columns)],
        columns=[column for column in config.categorical_columns if column in working.columns],
        dummy_na=True,
        dtype="float64",
    )
    treatment = working[config.treatment_column].astype(int).to_numpy()
    outcome = working[config.outcome_column].astype(float).to_numpy()
    weights = working[config.sample_weight_column].astype("float64").to_numpy()
    forest = CausalForestDML(
        model_y=RandomForestRegressor(n_estimators=100, random_state=config.random_state),
        model_t=RandomForestClassifier(n_estimators=100, random_state=config.random_state),
        discrete_treatment=True,
        n_estimators=100,
        min_samples_leaf=20,
        random_state=config.random_state,
    )
    forest.fit(Y=outcome, T=treatment, X=features, sample_weight=weights)
    effects = np.asarray(forest.effect(features), dtype="float64")
    return {
        "name": "causal_forest_dml",
        "status": "ok",
        "dependency": "econml",
        "rows": int(len(working)),
        "effect_mean": float(np.mean(effects)),
        "effect_std": float(np.std(effects)),
        "effect_p10": float(np.quantile(effects, 0.10)),
        "effect_p90": float(np.quantile(effects, 0.90)),
        "reason": (
            "Optional CausalForestDML CATE screen completed. Treat as exploratory and compare "
            "against subgroup diagnostics before interpreting."
        ),
    }


def _dowhy_heterogeneity_refuters_record() -> dict[str, Any]:
    if not _has_optional_dependency("dowhy"):
        return {
            "name": "dowhy_heterogeneity_refuters",
            "status": "skipped",
            "dependency": "dowhy",
            "reason": "Optional dependency `dowhy` is not installed in the default environment.",
        }
    return {
        "name": "dowhy_heterogeneity_refuters",
        "status": "not_run",
        "dependency": "dowhy",
        "reason": "No concrete DoWhy heterogeneity refuter is configured for PR23.",
    }


def _has_optional_dependency(import_name: str) -> bool:
    return importlib.util.find_spec(import_name) is not None


def _observed_levels(values: pd.Series) -> list[str]:
    string_values = values.astype("string")
    observed = string_values.loc[string_values.notna()]
    return sorted(str(item) for item in observed.unique().tolist())


def _level_mask(values: pd.Series, level: str) -> pd.Series:
    return values.astype("string") == level


def _age_band(values: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce")
    return pd.cut(
        numeric,
        bins=[17, 34, 49, 64, 120],
        labels=["18-34", "35-49", "50-64", "65+"],
        right=True,
    ).astype("string")


def _annual_aqi_band(values: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce")
    return pd.cut(
        numeric,
        bins=[-np.inf, 50, 100, 150, np.inf],
        labels=["0-50_good", "51-100_moderate", "101-150_unhealthy_sensitive", "151+_higher"],
        right=True,
    ).astype("string")


def _numeric_quantile_band(values: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce")
    non_null = numeric.dropna()
    if non_null.nunique() < 3:
        return pd.Series(pd.NA, index=values.index, dtype="string")
    lower = float(non_null.quantile(0.33))
    upper = float(non_null.quantile(0.67))
    if lower >= upper:
        return pd.Series(pd.NA, index=values.index, dtype="string")
    return pd.cut(
        numeric,
        bins=[-np.inf, lower, upper, np.inf],
        labels=["low", "middle", "high"],
        right=True,
    ).astype("string")


def _is_context_column(column: str) -> bool:
    return column.startswith(("acs_", "svi_", "epa_")) or column.endswith("_context")
