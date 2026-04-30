"""CLI-focused tests for the DuckDB views builder."""

from __future__ import annotations

import pytest

from longevity_lab.pipeline.build_duckdb_views import main


def test_years_only_requires_year_or_years() -> None:
    """--years-only should fail fast without a traceback if no year(s) are provided."""
    with pytest.raises(SystemExit) as exc:
        main(["--years-only"])
    assert exc.value.code == 2
