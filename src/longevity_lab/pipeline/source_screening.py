"""Validate optional data-source candidates and render screening summaries."""

from __future__ import annotations

import argparse
import ipaddress
from collections.abc import Sequence
from pathlib import Path
from typing import Literal, Self
from urllib.parse import urlparse

import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from longevity_lab.config_files import config_file_path

ScreenDecision = Literal[
    "reject",
    "watchlist",
    "context-only",
    "validation-only",
    "ready-for-ablation",
]
JoinFeasibilityLevel = Literal["none", "low", "medium", "high"]

EXPECTED_DECISIONS: tuple[ScreenDecision, ...] = (
    "reject",
    "watchlist",
    "context-only",
    "validation-only",
    "ready-for-ablation",
)


class AccessMethod(BaseModel):
    """Public-access and scriptability metadata for a candidate source."""

    model_config = ConfigDict(extra="forbid")

    method: str = Field(min_length=1)
    scriptable: bool
    credentials_required: bool
    manual_only: bool
    notes: str = Field(min_length=1)

    @model_validator(mode="after")
    def require_public_scriptable_access(self) -> Self:
        """Reject candidates that violate the local public-data guardrails."""
        if self.credentials_required:
            raise ValueError("Candidate sources must not require private credentials.")
        if self.manual_only:
            raise ValueError("Candidate sources must not require manual-only downloads.")
        if not self.scriptable:
            raise ValueError("Candidate sources must expose a scriptable access path.")
        return self


class GeographyTimeKeys(BaseModel):
    """Geography, time, and join-key metadata for a candidate source."""

    model_config = ConfigDict(extra="forbid")

    geographies: list[str] = Field(min_length=1)
    time_keys: list[str] = Field(min_length=1)
    join_keys: list[str] = Field(min_length=1)
    time_coverage: str = Field(min_length=1)
    notes: str = Field(min_length=1)


class JoinFeasibility(BaseModel):
    """First-pass join feasibility assessment."""

    model_config = ConfigDict(extra="forbid")

    level: JoinFeasibilityLevel
    notes: str = Field(min_length=1)


class RubricCriterion(BaseModel):
    """One source-screening rubric criterion."""

    model_config = ConfigDict(extra="forbid")

    criterion: str = Field(min_length=1)
    required_evidence: str = Field(min_length=1)
    pass_condition: str = Field(min_length=1)


class CandidateRubricAssessment(BaseModel):
    """Candidate-specific decision-rubric evidence."""

    model_config = ConfigDict(extra="forbid")

    public_access: str = Field(min_length=1)
    join_feasibility: str = Field(min_length=1)
    prior_signal_rationale: str = Field(min_length=1)
    bias_review: str = Field(min_length=1)
    operational_fit: str = Field(min_length=1)
    ablation_plan: str = Field(min_length=1)


class SourceCandidate(BaseModel):
    """Machine-readable metadata for one optional source-screen candidate."""

    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    source_url: str = Field(min_length=1)
    supporting_urls: list[str] = Field(default_factory=list)
    access_method: AccessMethod
    geography_time_keys: GeographyTimeKeys
    expected_size: str = Field(min_length=1)
    likely_features: list[str] = Field(min_length=1)
    target_outcomes: list[str] = Field(min_length=1)
    join_feasibility: JoinFeasibility
    bias_caveats: list[str] = Field(min_length=1)
    first_pass_decision: ScreenDecision
    decision_rationale: str = Field(min_length=1)
    rubric: CandidateRubricAssessment

    @field_validator("source_url")
    @classmethod
    def require_public_https_source_url(cls, value: str) -> str:
        """Require official source URLs to be public HTTPS URLs."""
        _require_public_https_url(value, "source_url")
        return value

    @field_validator("supporting_urls")
    @classmethod
    def require_public_https_supporting_urls(cls, values: list[str]) -> list[str]:
        """Require supporting URLs to be public HTTPS URLs."""
        for value in values:
            _require_public_https_url(value, "supporting_urls")
        return values


class SourceCandidateRegistry(BaseModel):
    """Versioned registry of optional source-screen candidates."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int
    screened_on: str = Field(min_length=1)
    decision_values: list[ScreenDecision] = Field(min_length=1)
    rubric: list[RubricCriterion] = Field(min_length=1)
    candidates: list[SourceCandidate] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_registry(self) -> Self:
        """Reject duplicate IDs and keep decision values aligned with the code contract."""
        if self.schema_version != 1:
            raise ValueError("schema_version must be 1.")
        if tuple(self.decision_values) != EXPECTED_DECISIONS:
            raise ValueError("decision_values must match the supported source-screening decisions.")
        self.by_id()
        return self

    def by_id(self) -> dict[str, SourceCandidate]:
        """Return candidates keyed by `source_id`, rejecting duplicates."""
        indexed: dict[str, SourceCandidate] = {}
        for candidate in self.candidates:
            if candidate.source_id in indexed:
                raise ValueError(
                    f"Duplicate source_id in candidate registry: {candidate.source_id}"
                )
            indexed[candidate.source_id] = candidate
        return indexed

    def decisions_by_source(self) -> dict[str, ScreenDecision]:
        """Return first-pass decisions keyed by source ID."""
        return {candidate.source_id: candidate.first_pass_decision for candidate in self.candidates}


def default_candidate_registry_path() -> Path:
    """Return the repo-local optional source candidate registry path."""
    return config_file_path("data_source_candidates.yaml")


def load_source_candidate_registry(path: Path | None = None) -> SourceCandidateRegistry:
    """Load and validate the YAML candidate registry."""
    registry_path = path or default_candidate_registry_path()
    payload = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Source candidate registry must be a YAML mapping.")
    return SourceCandidateRegistry.model_validate(payload)


def render_candidate_markdown(registry: SourceCandidateRegistry) -> str:
    """Render the candidate registry as a deterministic Markdown summary."""
    lines: list[str] = [
        "# Optional Data-Source Candidate Screen",
        "",
        f"Screened on: `{registry.screened_on}`",
        "",
        "This document is generated from `conf/data_source_candidates.yaml` by "
        "`pdm run python -m longevity_lab.pipeline.source_screening --output "
        "docs/data_source_candidate_screen.md`.",
        "",
        "No raw data is downloaded by this screen. Future ingestion PRs must pass this "
        "registry screen before adding a source to `conf/data_sources.yaml`.",
        "",
        "## Decision Rubric",
        "",
        "| Criterion | Required evidence | Pass condition |",
        "| --- | --- | --- |",
    ]
    for criterion in registry.rubric:
        lines.append(
            "| "
            f"{_table_cell(criterion.criterion)} | "
            f"{_table_cell(criterion.required_evidence)} | "
            f"{_table_cell(criterion.pass_condition)} |"
        )

    lines.extend(
        [
            "",
            "## First-Pass Decisions",
            "",
            "| Source | Decision | Join feasibility | Expected size |",
            "| --- | --- | --- | --- |",
        ]
    )
    for candidate in registry.candidates:
        lines.append(
            "| "
            f"{_table_cell(candidate.title)} | "
            f"`{candidate.first_pass_decision}` | "
            f"{candidate.join_feasibility.level} | "
            f"{_table_cell(candidate.expected_size)} |"
        )

    lines.extend(["", "## Candidate Details", ""])
    for candidate in registry.candidates:
        access = candidate.access_method
        geo = candidate.geography_time_keys
        lines.extend(
            [
                f"### {candidate.title}",
                "",
                f"- Source ID: `{candidate.source_id}`",
                f"- Decision: `{candidate.first_pass_decision}`",
                f"- Source URL: {candidate.source_url}",
            ]
        )
        if candidate.supporting_urls:
            lines.append(f"- Supporting URLs: {_join_inline(candidate.supporting_urls)}")
        lines.extend(
            [
                "- Access method: "
                f"{access.method}; scriptable={_yes_no(access.scriptable)}; "
                f"credentials_required={_yes_no(access.credentials_required)}; "
                f"manual_only={_yes_no(access.manual_only)}. {access.notes}",
                "- Geography/time keys: "
                f"geographies={_join_inline(geo.geographies)}; "
                f"time_keys={_join_inline(geo.time_keys)}; "
                f"join_keys={_join_inline(geo.join_keys)}; "
                f"time_coverage={_ensure_sentence(geo.time_coverage)} {geo.notes}",
                f"- Likely features: {_join_inline(candidate.likely_features)}",
                f"- Target outcomes: {_join_inline(candidate.target_outcomes)}",
                "- Join feasibility: "
                f"{candidate.join_feasibility.level}. {candidate.join_feasibility.notes}",
                f"- Bias caveats: {_join_inline(candidate.bias_caveats)}",
                f"- Decision rationale: {candidate.decision_rationale}",
                "- Rubric evidence: "
                f"public_access={candidate.rubric.public_access}; "
                f"join_feasibility={candidate.rubric.join_feasibility}; "
                f"prior_signal_rationale={candidate.rubric.prior_signal_rationale}; "
                f"bias_review={candidate.rubric.bias_review}; "
                f"operational_fit={candidate.rubric.operational_fit}; "
                f"ablation_plan={candidate.rubric.ablation_plan}",
                "",
            ]
        )

    return "\n".join(lines).rstrip() + "\n"


def build_parser() -> argparse.ArgumentParser:
    """Build the source-screening CLI parser."""
    parser = argparse.ArgumentParser(
        description="Validate optional data-source candidates and render a Markdown summary."
    )
    parser.add_argument(
        "--registry",
        type=Path,
        default=default_candidate_registry_path(),
        help="Candidate registry path.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional Markdown output path. Prints to stdout when omitted.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the source-screening CLI."""
    args = build_parser().parse_args(argv)
    registry = load_source_candidate_registry(args.registry)
    markdown = render_candidate_markdown(registry)
    if args.output is None:
        print(markdown, end="")
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(markdown, encoding="utf-8")
    print(f"Wrote source-screening summary: {args.output}")
    return 0


def _join_inline(items: Sequence[str]) -> str:
    return "; ".join(items)


def _table_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", "<br>")


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


def _ensure_sentence(value: str) -> str:
    stripped = value.rstrip()
    if stripped.endswith("."):
        return stripped
    return f"{stripped}."


def _require_public_https_url(value: str, field_name: str) -> None:
    parsed = urlparse(value)
    hostname = parsed.hostname or ""
    if parsed.scheme != "https" or not hostname:
        raise ValueError(f"{field_name} must be a public HTTPS URL.")
    if hostname in {"localhost", "127.0.0.1", "::1"} or hostname.endswith(".local"):
        raise ValueError(f"{field_name} must not point to a local host.")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        return
    if not address.is_global:
        raise ValueError(f"{field_name} must not point to a private or local IP address.")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
