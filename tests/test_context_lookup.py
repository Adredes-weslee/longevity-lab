"""Tests for state-year geography context lookup."""

from pathlib import Path

import pandas as pd  # type: ignore[import-untyped]

from longevity_lab.api.schemas import ScenarioGeographySelection
from longevity_lab.services.context_lookup import ContextLookupService


def test_context_lookup_missing_table_returns_safe_fallback_options(tmp_path: Path) -> None:
    """Missing processed context tables should not leak absolute local paths."""
    service = ContextLookupService(tmp_path / "data")

    response = service.get_geographies(year=2023)

    assert response.selected_year == 2023
    assert response.supported_levels == ["state"]
    assert response.readiness.active is False
    assert response.readiness.table_exists is False
    assert response.readiness.table_path == "processed/context/context_state_year.parquet"
    assert not Path(response.readiness.table_path).is_absolute()
    assert response.options
    assert all(option.level == "state" for option in response.options)
    assert all(option.context_available is False for option in response.options)


def test_context_lookup_reads_state_year_options(tmp_path: Path) -> None:
    """When the state-year table is present, options should come from matching rows."""
    data_dir = tmp_path / "data"
    table_path = data_dir / "processed" / "context" / "context_state_year.parquet"
    table_path.parent.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "year": 2022,
                "state_fips": "36",
                "geography_name": "New York",
                "acs_poverty_percent": 11.1,
            },
            {
                "year": 2023,
                "state_fips": "06",
                "geography_name": "California",
                "acs_poverty_percent": 12.5,
            },
        ]
    ).to_parquet(table_path, index=False)

    response = ContextLookupService(data_dir).get_geographies(year=2023)

    assert response.readiness.active is True
    assert response.readiness.table_exists is True
    assert response.readiness.year_available is True
    assert response.readiness.state_count == 1
    assert response.readiness.available_years == [2022, 2023]
    option_tuples = [
        (option.state_fips, option.label, option.context_available) for option in response.options
    ]
    assert option_tuples == [("06", "California", True)]


def test_lookup_state_context_returns_matching_context_features(tmp_path: Path) -> None:
    """The lookup service should expose trusted local context features separately."""
    data_dir = tmp_path / "data"
    table_path = data_dir / "processed" / "context" / "context_state_year.parquet"
    table_path.parent.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "year": 2023,
                "state_fips": "06",
                "geography_name": "California",
                "acs_poverty_percent": 12.5,
                "svi_overall_percentile": 0.42,
            }
        ]
    ).to_parquet(table_path, index=False)

    result = ContextLookupService(data_dir).lookup_state_context(
        ScenarioGeographySelection(level="state", state_fips="06", year=2023)
    )

    assert result.readiness.active is True
    assert result.context_features == {
        "acs_poverty_percent": 12.5,
        "svi_overall_percentile": 0.42,
    }
