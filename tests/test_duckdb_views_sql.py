"""Unit tests for SQL-literal helpers used by the DuckDB views builder."""

from longevity_lab.pipeline.build_duckdb_views import _sql_list_literal, _sql_quote


def test_sql_quote_escapes_single_quotes() -> None:
    """Escape embedded single quotes for DuckDB SQL string literals."""
    assert _sql_quote("a'b") == "'a''b'"


def test_sql_list_literal_quotes_values() -> None:
    """Quote each element inside DuckDB list literals."""
    assert _sql_list_literal(["a", "b"]) == "['a', 'b']"
