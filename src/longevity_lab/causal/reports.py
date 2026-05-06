"""Report writer and CLI for the non-serving causal workbench."""

from __future__ import annotations

import argparse
import datetime as dt
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from longevity_lab.causal.datasets import (
    CausalWorkbenchConfig,
    PreparedCausalDataset,
    load_causal_config_for_question,
    load_causal_workbench_config,
    load_smoking_lung_config,
    prepare_causal_dataset,
    resolve_repo_path,
)
from longevity_lab.causal.estimators import estimate_causal_effect


@dataclass(frozen=True, slots=True)
class CausalReportResult:
    """Paths produced by one causal workbench run."""

    json_path: Path
    markdown_path: Path


def run_smoking_lung_workbench(
    *,
    config: CausalWorkbenchConfig | None = None,
    input_path: Path | None = None,
    output_dir: Path | None = None,
) -> CausalReportResult:
    """Run the PR12 smoking-to-lung-disease workbench and write reports."""
    causal_config = config or load_smoking_lung_config()
    return run_causal_workbench(config=causal_config, input_path=input_path, output_dir=output_dir)


def run_causal_workbench(
    *,
    config: CausalWorkbenchConfig,
    input_path: Path | None = None,
    output_dir: Path | None = None,
) -> CausalReportResult:
    """Run one configured non-serving causal workbench question and write reports."""
    report_output_dir = resolve_repo_path(output_dir) if output_dir else config.output_dir
    report_output_dir.mkdir(parents=True, exist_ok=True)
    try:
        prepared = prepare_causal_dataset(input_path=input_path, config=config)
    except (FileNotFoundError, ValueError) as exc:
        payload = _build_preparation_failure_payload(config=config, reason=str(exc))
        return _write_payload(payload=payload, config=config, report_output_dir=report_output_dir)

    estimated = estimate_causal_effect(prepared, config)

    payload = _build_report_payload(
        config=config,
        prepared=prepared,
        estimate=estimated["estimate"],
        diagnostics=estimated["diagnostics"],
        refutations=estimated["refutations"],
    )
    return _write_payload(payload=payload, config=config, report_output_dir=report_output_dir)


def _write_payload(
    *,
    payload: dict[str, Any],
    config: CausalWorkbenchConfig,
    report_output_dir: Path,
) -> CausalReportResult:
    json_path = report_output_dir / config.json_name
    markdown_path = report_output_dir / config.markdown_name
    json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(_render_markdown(payload), encoding="utf-8")
    return CausalReportResult(json_path=json_path, markdown_path=markdown_path)


def main(argv: list[str] | None = None) -> None:
    """CLI entrypoint for writing non-serving causal workbench reports."""
    parser = argparse.ArgumentParser(description="Run a non-serving causal workbench report.")
    parser.add_argument(
        "--question",
        default="smoking_lung",
        help=(
            "Causal question id or alias (default: smoking_lung). "
            "Supported aliases include activity_diabetes."
        ),
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Concrete causal workbench config path. Overrides --question.",
    )
    parser.add_argument(
        "--input-path",
        type=Path,
        default=None,
        help="Optional CSV/Parquet integrated person-year input override.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Optional report output directory override.",
    )
    args = parser.parse_args(argv)
    config = (
        load_causal_workbench_config(args.config)
        if args.config
        else load_causal_config_for_question(str(args.question))
    )
    result = run_causal_workbench(
        config=config,
        input_path=args.input_path,
        output_dir=args.output_dir,
    )
    print(f"Wrote causal JSON report: {result.json_path}")
    print(f"Wrote causal Markdown report: {result.markdown_path}")


def _build_report_payload(
    *,
    config: CausalWorkbenchConfig,
    prepared: PreparedCausalDataset,
    estimate: dict[str, Any] | None,
    diagnostics: dict[str, Any],
    refutations: list[dict[str, Any]],
) -> dict[str, Any]:
    report_status = (
        "failed_diagnostic"
        if estimate is None or diagnostics["diagnostic_gate"]["status"] == "failed"
        else "exploratory_assumption_bound"
    )
    return {
        "schema_version": 1,
        "created_at": dt.datetime.now(dt.UTC).isoformat(),
        "question_id": config.question_id,
        "title": config.title,
        "source_question_registry": str(config.source_question_registry),
        "run_config_path": str(config.config_path),
        "status": report_status,
        "serving_policy": {
            "api_exposed": False,
            "ui_exposed": False,
            "statement": "Not served through the FastAPI API or React UI.",
        },
        "analysis_dataset": {
            "source_path": str(prepared.source_path),
            "input_rows": prepared.input_rows,
            "rows": prepared.analysis_rows,
            "exclusions": prepared.exclusions,
            "missingness": prepared.missingness,
            "sample_weight_column": config.sample_weight_column,
            "weight_imputation": prepared.weight_imputation,
        },
        "question": {
            "treatment": {
                "name": config.treatment_name,
                "column": config.treatment_column,
                "contrast": config.treatment_contrast,
                "derivation": config.treatment_derivation,
            },
            "outcome": {
                "name": config.outcome_name,
                "column": config.outcome_column,
                "timing": config.outcome_timing,
            },
            "estimand": config.estimand,
            "adjustment_columns": list(config.adjustment_columns),
            "excluded_columns": list(config.excluded_columns),
        },
        "dag": {
            "version": config.dag_version,
            "key_edges": list(config.dag_edges),
            "residual_risks": list(config.residual_risks),
        },
        "assumptions": list(config.assumptions),
        "diagnostics": diagnostics,
        "estimate": estimate,
        "refutations": refutations,
        "negative_controls": {
            "outcomes": _negative_control_outcome_statuses(config, report_status),
            "exposures": _negative_control_exposure_statuses(config, refutations, report_status),
        },
        "sensitivity_checks": _sensitivity_check_statuses(config, refutations, report_status),
        "limitations": _limitations(config),
    }


def _build_preparation_failure_payload(
    *,
    config: CausalWorkbenchConfig,
    reason: str,
) -> dict[str, Any]:
    diagnostics: dict[str, Any] = {
        "missingness": {},
        "weight_imputation": {},
        "diagnostic_gate": {
            "status": "failed",
            "warnings": [f"Dataset preparation failed: {reason}"],
            "rows_inside_configured_overlap": 0,
            "total_rows": 0,
        },
        "propensity_overlap": None,
        "top_standardized_mean_differences": [],
    }
    refutations = [
        {
            "name": name,
            "status": "failed_diagnostic",
            "note": f"Not run because dataset preparation failed: {reason}",
            "rows": 0,
        }
        for name in (
            "permuted_treatment_placebo",
            "subset_refit",
            "random_common_cause",
            "overlap_trimmed_refit",
        )
    ]
    return {
        "schema_version": 1,
        "created_at": dt.datetime.now(dt.UTC).isoformat(),
        "question_id": config.question_id,
        "title": config.title,
        "source_question_registry": str(config.source_question_registry),
        "run_config_path": str(config.config_path),
        "status": "failed_diagnostic",
        "serving_policy": {
            "api_exposed": False,
            "ui_exposed": False,
            "statement": "Not served through the FastAPI API or React UI.",
        },
        "analysis_dataset": {
            "source_path": None,
            "input_rows": 0,
            "rows": 0,
            "exclusions": {"dataset_preparation_failed": reason},
            "missingness": {},
            "sample_weight_column": config.sample_weight_column,
            "weight_imputation": {},
        },
        "question": {
            "treatment": {
                "name": config.treatment_name,
                "column": config.treatment_column,
                "contrast": config.treatment_contrast,
                "derivation": config.treatment_derivation,
            },
            "outcome": {
                "name": config.outcome_name,
                "column": config.outcome_column,
                "timing": config.outcome_timing,
            },
            "estimand": config.estimand,
            "adjustment_columns": list(config.adjustment_columns),
            "excluded_columns": list(config.excluded_columns),
        },
        "dag": {
            "version": config.dag_version,
            "key_edges": list(config.dag_edges),
            "residual_risks": list(config.residual_risks),
        },
        "assumptions": list(config.assumptions),
        "diagnostics": diagnostics,
        "estimate": None,
        "refutations": refutations,
        "negative_controls": {
            "outcomes": _negative_control_outcome_statuses(config, "failed_diagnostic"),
            "exposures": _negative_control_exposure_statuses(
                config,
                refutations,
                "failed_diagnostic",
            ),
        },
        "sensitivity_checks": _sensitivity_check_statuses(
            config,
            refutations,
            "failed_diagnostic",
        ),
        "limitations": _limitations(config),
    }


def _limitations(config: CausalWorkbenchConfig) -> list[str]:
    cross_sectional_reverse_causation = (
        "Reverse causation remains plausible because the treatment and outcome are cross-sectional."
    )
    return [
        "BRFSS is cross-sectional and self-reported.",
        "The estimate depends on no unmeasured confounding after the recorded adjustment set.",
        (
            "Former smokers are included in the not-current-smoker reference for the primary "
            "contrast."
        )
        if config.question_id == "smoking_chronic_lung_disease"
        else cross_sectional_reverse_causation,
        "This report is not medical advice and does not change predictive Explorer scores.",
    ]


def _render_markdown(payload: dict[str, Any]) -> str:
    estimate = payload["estimate"]
    diagnostics = payload["diagnostics"]
    overlap = diagnostics["propensity_overlap"]
    estimator_name = str(estimate["method"]) if isinstance(estimate, dict) else "not_estimated"
    lines = [
        f"# {payload['title']}",
        "",
        f"Generated: `{payload['created_at']}`",
        "",
        "## Boundary",
        "",
        "Not served through the FastAPI API or React UI. These exploratory causal estimates are "
        "separate from predictive Explorer scenario deltas.",
        "",
        "## Question",
        "",
        f"- Run config: `{payload['run_config_path']}`",
        f"- Treatment: `{payload['question']['treatment']['column']}` "
        f"({payload['question']['treatment']['contrast']})",
        "- Treatment derivation: "
        f"`{json.dumps(payload['question']['treatment']['derivation'], sort_keys=True)}`",
        f"- Outcome: `{payload['question']['outcome']['column']}` "
        f"({payload['question']['outcome']['timing']})",
        f"- Estimator: `{estimator_name}`",
        f"- Adjustment columns: {', '.join(payload['question']['adjustment_columns'])}",
        "",
        "## Analysis Data",
        "",
        f"- Source: `{payload['analysis_dataset']['source_path']}`",
        f"- Rows after exclusions: {payload['analysis_dataset']['rows']}",
        f"- Exclusions: `{json.dumps(payload['analysis_dataset']['exclusions'], sort_keys=True)}`",
        "",
        "## Estimate",
        "",
    ]
    if isinstance(estimate, dict):
        lines.extend(
            [
                f"- Adjusted treated risk: {estimate['adjusted_treated_risk']:.4f}",
                f"- Adjusted control risk: {estimate['adjusted_control_risk']:.4f}",
                f"- Risk difference: {estimate['risk_difference']:.4f}",
                f"- Risk ratio: {_format_optional_float(estimate['risk_ratio'])}",
                f"- Odds ratio: {_format_optional_float(estimate['odds_ratio'])}",
            ]
        )
    else:
        warnings = diagnostics["diagnostic_gate"].get("warnings", [])
        lines.append(f"- Not estimated: {'; '.join(str(item) for item in warnings)}")
    lines.extend(
        [
            "",
            "## Diagnostics",
            "",
            f"- Diagnostic gate: `{diagnostics['diagnostic_gate']['status']}`",
        ]
    )
    if isinstance(overlap, dict):
        lines.extend(
            [
                f"- Treated/control rows: {overlap['treated_rows']} / {overlap['control_rows']}",
                f"- Propensity range: {overlap['min']:.4f} to {overlap['max']:.4f}",
                f"- Rows inside configured overlap: {overlap['rows_inside_configured_overlap']}",
            ]
        )
    else:
        lines.append("- Propensity overlap: not available because diagnostics failed.")
    lines.extend(
        [
            "",
            "Top absolute standardized mean differences:",
            "",
        ]
    )
    for item in diagnostics["top_standardized_mean_differences"][:5]:
        lines.append(f"- `{item['feature']}`: {item['abs_standardized_mean_difference']:.4f}")
    lines.extend(
        [
            "",
            "## Refutations",
            "",
        ]
    )
    for item in payload["refutations"]:
        if item["status"] == "ok":
            lines.append(
                f"- `{item['name']}`: risk difference {item['risk_difference']:.4f}; "
                f"delta from primary {item['difference_from_primary']:.4f}"
            )
        else:
            lines.append(f"- `{item['name']}`: {item['status']} ({item['note']})")
    lines.extend(
        [
            "",
            "## Negative Controls",
            "",
            "Outcome checks:",
            "",
        ]
    )
    for item in payload["negative_controls"]["outcomes"]:
        lines.append(f"- `{item['name']}`: {item['status']} ({item['reason']})")
    lines.extend(
        [
            "",
            "Exposure checks:",
            "",
        ]
    )
    for item in payload["negative_controls"]["exposures"]:
        lines.append(f"- `{item['name']}`: {item['status']} ({item['reason']})")
    lines.extend(
        [
            "",
            "## Sensitivity Checks",
            "",
        ]
    )
    for item in payload["sensitivity_checks"]:
        lines.append(f"- `{item['name']}`: {item['status']} ({item['reason']})")
    lines.extend(
        [
            "",
            "## Limitations",
            "",
        ]
    )
    lines.extend(f"- {limitation}" for limitation in payload["limitations"])
    return "\n".join(lines) + "\n"


def _negative_control_outcome_statuses(
    config: CausalWorkbenchConfig,
    report_status: str,
) -> list[dict[str, str]]:
    """Return explicit statuses for PR11 negative-control outcomes."""
    if report_status == "failed_diagnostic":
        return [
            {
                "name": outcome,
                "status": "failed_diagnostic",
                "reason": "Not run because primary diagnostic prerequisites failed.",
            }
            for outcome in config.negative_control_outcomes
        ]
    return [
        {
            "name": outcome,
            "status": "not_run",
            "reason": (
                "No concrete negative-control outcome column is configured for this PR22 "
                "workbench run."
            ),
        }
        for outcome in config.negative_control_outcomes
    ]


def _negative_control_exposure_statuses(
    config: CausalWorkbenchConfig,
    refutations: list[dict[str, Any]],
    report_status: str,
) -> list[dict[str, str]]:
    """Return explicit statuses for PR11 negative-control exposures."""
    _ = refutations
    statuses: list[dict[str, str]] = []
    for exposure in config.negative_control_exposures:
        if exposure.startswith("within_stratum_permuted_"):
            statuses.append(
                {
                    "name": exposure,
                    "status": (
                        "failed_diagnostic" if report_status == "failed_diagnostic" else "not_run"
                    ),
                    "reason": (
                        "Configured as a within-stratum placebo exposure, but PR22 only runs "
                        "a global permutation refutation and does not report it as this "
                        "negative-control exposure."
                    ),
                }
            )
            continue
        statuses.append(
            {
                "name": exposure,
                "status": (
                    "failed_diagnostic" if report_status == "failed_diagnostic" else "not_run"
                ),
                "reason": "No concrete placebo threshold implementation is configured.",
            }
        )
    return statuses


def _sensitivity_check_statuses(
    config: CausalWorkbenchConfig,
    refutations: list[dict[str, Any]],
    report_status: str,
) -> list[dict[str, str]]:
    """Return explicit status for every configured sensitivity check."""
    if report_status == "failed_diagnostic":
        return [
            {
                "name": check,
                "status": "failed_diagnostic",
                "reason": "Not run because primary diagnostic prerequisites failed.",
            }
            for check in config.sensitivity_checks
        ]
    refutation_by_name = {str(item["name"]): item for item in refutations}
    statuses: list[dict[str, str]] = []
    for check in config.sensitivity_checks:
        if check == "dowhy_placebo_subset_random_common_cause_refutations":
            statuses.append(_dowhy_refutation_status(refutation_by_name))
            continue
        if check in refutation_by_name:
            statuses.append(
                {
                    "name": check,
                    "status": str(refutation_by_name[check]["status"]),
                    "reason": str(refutation_by_name[check]["note"]),
                }
            )
        else:
            statuses.append(
                {
                    "name": check,
                    "status": "not_run",
                    "reason": "Configured in PR11 but not implemented in the PR22 workbench.",
                }
            )
    return statuses


def _dowhy_refutation_status(refutation_by_name: dict[str, dict[str, Any]]) -> dict[str, str]:
    implemented = ("permuted_treatment_placebo", "subset_refit", "random_common_cause")
    missing = [name for name in implemented if name not in refutation_by_name]
    if missing:
        return {
            "name": "dowhy_placebo_subset_random_common_cause_refutations",
            "status": "skipped",
            "reason": f"Missing prototype refutation outputs: {', '.join(missing)}.",
        }
    statuses = {str(refutation_by_name[name]["status"]) for name in implemented}
    status = "ok" if statuses == {"ok"} else "warning"
    return {
        "name": "dowhy_placebo_subset_random_common_cause_refutations",
        "status": status,
        "reason": (
            "Implemented in PR12 through permuted-treatment placebo, subset-refit, "
            "and random-common-cause refutation prototypes."
        ),
    }


def _format_optional_float(value: object) -> str:
    if value is None:
        return "not estimable"
    if isinstance(value, int | float):
        return f"{float(value):.4f}"
    return f"{float(str(value)):.4f}"


if __name__ == "__main__":
    main()
