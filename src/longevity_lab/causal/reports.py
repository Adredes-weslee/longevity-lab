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
    load_smoking_lung_config,
    prepare_smoking_lung_dataset,
    resolve_repo_path,
)
from longevity_lab.causal.estimators import estimate_smoking_lung_effect


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
    prepared = prepare_smoking_lung_dataset(input_path=input_path, config=causal_config)
    estimated = estimate_smoking_lung_effect(prepared, causal_config)
    report_output_dir = resolve_repo_path(output_dir) if output_dir else causal_config.output_dir
    report_output_dir.mkdir(parents=True, exist_ok=True)

    payload = _build_report_payload(
        config=causal_config,
        prepared=prepared,
        estimate=estimated["estimate"],
        diagnostics=estimated["diagnostics"],
        refutations=estimated["refutations"],
    )
    json_path = report_output_dir / causal_config.json_name
    markdown_path = report_output_dir / causal_config.markdown_name
    json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(_render_markdown(payload), encoding="utf-8")
    return CausalReportResult(json_path=json_path, markdown_path=markdown_path)


def main(argv: list[str] | None = None) -> None:
    """CLI entrypoint for writing the smoking causal workbench report."""
    parser = argparse.ArgumentParser(
        description="Run the non-serving smoking-to-chronic-lung-disease causal workbench."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Causal workbench config path (default: conf/causal/smoking_lung.yaml).",
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
    config = load_smoking_lung_config(args.config) if args.config else load_smoking_lung_config()
    result = run_smoking_lung_workbench(
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
    estimate: dict[str, Any],
    diagnostics: dict[str, Any],
    refutations: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "created_at": dt.datetime.now(dt.UTC).isoformat(),
        "question_id": config.question_id,
        "title": config.title,
        "source_question_registry": str(config.source_question_registry),
        "status": "exploratory_assumption_bound",
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
            "outcomes": _negative_control_outcome_statuses(config),
            "exposures": _negative_control_exposure_statuses(config),
        },
        "sensitivity_checks": _sensitivity_check_statuses(config, refutations),
        "limitations": [
            "BRFSS is cross-sectional and self-reported.",
            "The estimate depends on no unmeasured confounding after the recorded adjustment set.",
            (
                "Former smokers are included in the not-current-smoker reference for the "
                "primary contrast."
            ),
            "This report is not medical advice and does not change predictive Explorer scores.",
        ],
    }


def _render_markdown(payload: dict[str, Any]) -> str:
    estimate = payload["estimate"]
    diagnostics = payload["diagnostics"]
    overlap = diagnostics["propensity_overlap"]
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
        f"- Treatment: `{payload['question']['treatment']['column']}` "
        f"({payload['question']['treatment']['contrast']})",
        f"- Outcome: `{payload['question']['outcome']['column']}` "
        f"({payload['question']['outcome']['timing']})",
        f"- Estimator: `{estimate['method']}`",
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
        f"- Adjusted treated risk: {estimate['adjusted_treated_risk']:.4f}",
        f"- Adjusted control risk: {estimate['adjusted_control_risk']:.4f}",
        f"- Risk difference: {estimate['risk_difference']:.4f}",
        f"- Risk ratio: {_format_optional_float(estimate['risk_ratio'])}",
        f"- Odds ratio: {_format_optional_float(estimate['odds_ratio'])}",
        "",
        "## Diagnostics",
        "",
        f"- Diagnostic gate: `{diagnostics['diagnostic_gate']['status']}`",
        f"- Treated/control rows: {overlap['treated_rows']} / {overlap['control_rows']}",
        f"- Propensity range: {overlap['min']:.4f} to {overlap['max']:.4f}",
        f"- Rows inside configured overlap: {overlap['rows_inside_configured_overlap']}",
        "",
        "Top absolute standardized mean differences:",
        "",
    ]
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
            lines.append(f"- `{item['name']}`: skipped ({item['note']})")
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


def _negative_control_outcome_statuses(config: CausalWorkbenchConfig) -> list[dict[str, str]]:
    """Return explicit statuses for PR11 negative-control outcomes."""
    return [
        {
            "name": outcome,
            "status": "skipped",
            "reason": (
                "Not run in PR12 prototype; retained from PR11 as a required future "
                "negative-control outcome check."
            ),
        }
        for outcome in config.negative_control_outcomes
    ]


def _negative_control_exposure_statuses(config: CausalWorkbenchConfig) -> list[dict[str, str]]:
    """Return explicit statuses for PR11 negative-control exposures."""
    return [
        {
            "name": exposure,
            "status": "ok" if exposure == "within_stratum_permuted_smoking_status" else "skipped",
            "reason": (
                "Implemented as `permuted_treatment_placebo` with a fixed seed."
                if exposure == "within_stratum_permuted_smoking_status"
                else "Configured in PR11 but not implemented in the PR12 prototype."
            ),
        }
        for exposure in config.negative_control_exposures
    ]


def _sensitivity_check_statuses(
    config: CausalWorkbenchConfig,
    refutations: list[dict[str, Any]],
) -> list[dict[str, str]]:
    """Return explicit status for every configured sensitivity check."""
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
                    "status": "skipped",
                    "reason": "Configured in PR11 but not implemented in the PR12 prototype.",
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
