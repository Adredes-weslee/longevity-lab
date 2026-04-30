"""Generate tiny synthetic sample data for dev/testing.

The sample is intentionally synthetic (not a subset of BRFSS records) so it can be
committed safely under `data/sample/` without shipping large datasets.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np  # type: ignore[import-untyped]
import pandas as pd  # type: ignore[import-untyped]

from longevity_lab.pipeline.common import add_common_pipeline_args, parse_years_from_args


def generate_integrated_sample(*, year: int, rows: int, seed: int) -> pd.DataFrame:
    """Return a tiny synthetic integrated_person_year-like table."""
    rng = np.random.default_rng(seed)
    state_choices = np.array(["01", "06", "12", "36", "48"], dtype=object)

    ages = rng.integers(low=18, high=91, size=rows)
    bmi = rng.uniform(low=18.0, high=40.0, size=rows).round(1)
    smoker = rng.random(size=rows) < 0.15
    alcohol = rng.integers(low=0, high=21, size=rows)
    exercise = rng.integers(low=0, high=601, size=rows)
    annual_aqi = rng.integers(low=25, high=151, size=rows)

    labels = {
        "label_heart_disease": (rng.random(size=rows) < 0.08).astype(int),
        "label_chronic_lung_disease": (rng.random(size=rows) < 0.06).astype(int),
        "label_stroke": (rng.random(size=rows) < 0.03).astype(int),
        "label_depression": (rng.random(size=rows) < 0.15).astype(int),
        "label_diabetes": (rng.random(size=rows) < 0.12).astype(int),
    }

    frame = pd.DataFrame(
        {
            "year": year,
            "state_fips": rng.choice(state_choices, size=rows),
            "age": ages,
            "bmi": bmi,
            "smoker": smoker,
            "alcohol_servings_per_week": alcohol,
            "exercise_minutes_per_week": exercise,
            "annual_aqi": annual_aqi,
            **labels,
            "survey_weight": rng.uniform(low=0.1, high=100.0, size=rows).round(4),
        }
    )
    return frame


def main(argv: list[str] | None = None) -> None:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description="Generate tiny synthetic sample data (tracked).")
    add_common_pipeline_args(parser)
    parser.add_argument("--rows", type=int, default=200, help="Number of rows to generate.")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility.")
    args = parser.parse_args(argv)

    years = parse_years_from_args(args)
    if len(years) != 1:
        raise ValueError("Sample generator expects exactly one year (use --year).")
    year = years[0]

    sample = generate_integrated_sample(year=year, rows=int(args.rows), seed=int(args.seed))
    out_path = Path(args.base_dir) / "sample" / "integrated_person_year_sample.csv"
    print(f"Write sample: {out_path} ({len(sample)} rows)")
    if args.dry_run:
        print("DRY RUN: write skipped")
        return

    out_path.parent.mkdir(parents=True, exist_ok=True)
    sample.to_csv(out_path, index=False, lineterminator="\n")


if __name__ == "__main__":
    main()
