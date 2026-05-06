"""Tests for optional source-screening registry and CLI output."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from longevity_lab.pipeline.source_screening import (
    EXPECTED_DECISIONS,
    SourceCandidateRegistry,
    load_source_candidate_registry,
    main,
    render_candidate_markdown,
)


def test_source_candidate_registry_loads_default_candidates() -> None:
    """The default registry should screen exactly the PR 28 candidate sources."""
    registry = load_source_candidate_registry()
    indexed = registry.by_id()

    assert registry.schema_version == 1
    assert tuple(registry.decision_values) == EXPECTED_DECISIONS
    assert set(indexed) == {
        "ahrq_clh_database",
        "usda_food_environment_food_access",
        "county_health_rankings",
        "cdc_wonder_mortality",
        "cdc_nhanes_public",
        "cdc_nhis_public",
    }
    assert registry.decisions_by_source() == {
        "ahrq_clh_database": "watchlist",
        "usda_food_environment_food_access": "ready-for-ablation",
        "county_health_rankings": "context-only",
        "cdc_wonder_mortality": "validation-only",
        "cdc_nhanes_public": "validation-only",
        "cdc_nhis_public": "watchlist",
    }


def test_source_candidates_have_required_guardrail_metadata() -> None:
    """Every screened candidate should be public, scriptable, caveated, and decided."""
    registry = load_source_candidate_registry()

    for candidate in registry.candidates:
        assert candidate.source_url.startswith("https://")
        assert candidate.access_method.scriptable is True
        assert candidate.access_method.credentials_required is False
        assert candidate.access_method.manual_only is False
        assert candidate.geography_time_keys.join_keys
        assert candidate.expected_size
        assert candidate.likely_features
        assert candidate.target_outcomes
        assert candidate.bias_caveats
        assert candidate.first_pass_decision in EXPECTED_DECISIONS
        assert candidate.rubric.public_access
        assert candidate.rubric.join_feasibility
        assert candidate.rubric.prior_signal_rationale
        assert candidate.rubric.bias_review
        assert candidate.rubric.operational_fit
        assert candidate.rubric.ablation_plan


def test_candidate_registry_rejects_missing_required_fields(tmp_path: Path) -> None:
    """Missing required registry fields should fail validation before a summary is written."""
    payload = _registry_payload()
    del payload["candidates"][0]["target_outcomes"]
    path = tmp_path / "candidates.yaml"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="target_outcomes"):
        load_source_candidate_registry(path)


def test_candidate_registry_loads_standard_yaml(tmp_path: Path) -> None:
    """The registry loader should support YAML syntax, not only JSON-compatible YAML."""
    path = tmp_path / "candidates.yaml"
    path.write_text(
        """
schema_version: 1
screened_on: "2026-05-06"
decision_values:
  - reject
  - watchlist
  - context-only
  - validation-only
  - ready-for-ablation
rubric:
  - criterion: Public access
    required_evidence: official public URL
    pass_condition: scriptable public access
candidates:
  - source_id: example_source
    title: Example Source
    source_url: https://example.gov/data
    supporting_urls: []
    access_method:
      method: direct download
      scriptable: true
      credentials_required: false
      manual_only: false
      notes: test
    geography_time_keys:
      geographies:
        - state
      time_keys:
        - year
      join_keys:
        - state_fips
        - year
      time_coverage: "2023"
      notes: test
    expected_size: small
    likely_features:
      - feature
    target_outcomes:
      - outcome
    join_feasibility:
      level: high
      notes: test
    bias_caveats:
      - test caveat
    first_pass_decision: watchlist
    decision_rationale: test rationale
    rubric:
      public_access: pass
      join_feasibility: pass
      prior_signal_rationale: test
      bias_review: test
      operational_fit: test
      ablation_plan: test
""".lstrip(),
        encoding="utf-8",
    )

    registry = load_source_candidate_registry(path)

    assert registry.by_id()["example_source"].first_pass_decision == "watchlist"


def test_candidate_registry_rejects_duplicate_source_ids(tmp_path: Path) -> None:
    """Duplicate candidate IDs should fail rather than silently shadowing records."""
    payload = _registry_payload()
    duplicate = dict(payload["candidates"][0])
    payload["candidates"].append(duplicate)
    path = tmp_path / "candidates.yaml"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="Duplicate source_id"):
        load_source_candidate_registry(path)


def test_candidate_registry_rejects_unknown_fields() -> None:
    """The source-screening schema should be strict to catch misspelled metadata."""
    payload = _registry_payload()
    payload["unexpected"] = True

    with pytest.raises(ValueError):
        SourceCandidateRegistry.model_validate(payload)


def test_candidate_registry_rejects_missing_schema_version() -> None:
    """A versioned registry must declare the schema version explicitly."""
    payload = _registry_payload()
    del payload["schema_version"]

    with pytest.raises(ValueError, match="schema_version"):
        SourceCandidateRegistry.model_validate(payload)


def test_candidate_registry_rejects_unsupported_schema_version() -> None:
    """Unsupported registry schema versions should fail before rendering docs."""
    payload = _registry_payload()
    payload["schema_version"] = 2

    with pytest.raises(ValueError, match="schema_version must be 1"):
        SourceCandidateRegistry.model_validate(payload)


def test_candidate_registry_rejects_non_https_urls() -> None:
    """Candidate URLs must be public HTTPS endpoints, not local files or hosts."""
    payload = _registry_payload()
    payload["candidates"][0]["source_url"] = "not-a-url"
    payload["candidates"][0]["supporting_urls"] = ["file:///C:/secret.csv"]

    with pytest.raises(ValueError, match="public HTTPS URL"):
        SourceCandidateRegistry.model_validate(payload)


@pytest.mark.parametrize(
    "url",
    [
        "https://10.0.0.1/data",
        "https://169.254.169.254/latest",
        "https://[::1]/data",
    ],
)
def test_candidate_registry_rejects_private_ip_urls(url: str) -> None:
    """Public-source URLs must not point to private or link-local IP endpoints."""
    payload = _registry_payload()
    payload["candidates"][0]["source_url"] = url

    with pytest.raises(ValueError, match="private or local IP|local host"):
        SourceCandidateRegistry.model_validate(payload)


def test_candidate_registry_rejects_non_scriptable_access() -> None:
    """Manual-only or non-scriptable candidate sources are outside PR 28 scope."""
    payload = _registry_payload()
    payload["candidates"][0]["access_method"]["scriptable"] = False

    with pytest.raises(ValueError, match="scriptable"):
        SourceCandidateRegistry.model_validate(payload)


def test_render_candidate_markdown_contains_rubric_and_decisions() -> None:
    """The Markdown summary should expose the rubric and one decision row per source."""
    registry = load_source_candidate_registry()
    markdown = render_candidate_markdown(registry)

    assert "# Optional Data-Source Candidate Screen" in markdown
    assert "No raw data is downloaded by this screen." in markdown
    assert "| Public access |" in markdown
    assert "| USDA ERS Food Environment Atlas and Food Access Research Atlas |" in markdown
    assert "`ready-for-ablation`" in markdown
    assert "CDC WONDER Mortality Query API" in markdown
    assert "`validation-only`" in markdown


def test_source_screening_cli_writes_markdown_summary(tmp_path: Path) -> None:
    """The CLI should validate the registry and write a deterministic Markdown summary."""
    output_path = tmp_path / "candidate_screen.md"

    exit_code = main(["--output", str(output_path)])

    assert exit_code == 0
    markdown = output_path.read_text(encoding="utf-8")
    assert "generated from `conf/data_source_candidates.yaml`" in markdown
    assert "Future ingestion PRs must pass this registry screen" in markdown


def _registry_payload() -> dict[str, Any]:
    """Return a minimal valid candidate registry payload for validation tests."""
    return {
        "schema_version": 1,
        "screened_on": "2026-05-06",
        "decision_values": list(EXPECTED_DECISIONS),
        "rubric": [
            {
                "criterion": "Public access",
                "required_evidence": "official public URL",
                "pass_condition": "scriptable public access",
            }
        ],
        "candidates": [
            {
                "source_id": "example_source",
                "title": "Example Source",
                "source_url": "https://example.gov/data",
                "supporting_urls": [],
                "access_method": {
                    "method": "direct download",
                    "scriptable": True,
                    "credentials_required": False,
                    "manual_only": False,
                    "notes": "test",
                },
                "geography_time_keys": {
                    "geographies": ["state"],
                    "time_keys": ["year"],
                    "join_keys": ["state_fips", "year"],
                    "time_coverage": "2023",
                    "notes": "test",
                },
                "expected_size": "small",
                "likely_features": ["feature"],
                "target_outcomes": ["outcome"],
                "join_feasibility": {
                    "level": "high",
                    "notes": "test",
                },
                "bias_caveats": ["test caveat"],
                "first_pass_decision": "watchlist",
                "decision_rationale": "test rationale",
                "rubric": {
                    "public_access": "pass",
                    "join_feasibility": "pass",
                    "prior_signal_rationale": "test",
                    "bias_review": "test",
                    "operational_fit": "test",
                    "ablation_plan": "test",
                },
            }
        ],
    }
