"""Build processed BRFSS tables (v1: brfss_person.parquet)."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np  # type: ignore[import-untyped]
import pandas as pd  # type: ignore[import-untyped]
import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.parquet as pq  # type: ignore[import-untyped]

from longevity_lab.pipeline.common import (
    FileProvenance,
    add_common_pipeline_args,
    collect_file_provenance,
    parse_years_from_args,
    require_columns,
    write_provenance_json,
)
from longevity_lab.pipeline.ingest import build_ingest_paths

RAW_COLUMNS: tuple[str, ...] = (
    "_STATE",
    "_AGEG5YR",
    "_BMI5",
    "_SMOKER3",
    "_DRNKWK2",
    "PA3MIN_",
    "_MICHD",
    "CHCCOPD3",
    "CVDSTRK3",
    "ADDEPEV3",
    "DIABETE4",
    "_LLCPWT",
)

AGE_MIDPOINT_BY_GROUP: dict[int, int] = {
    1: 21,
    2: 27,
    3: 32,
    4: 37,
    5: 42,
    6: 47,
    7: 52,
    8: 57,
    9: 62,
    10: 67,
    11: 72,
    12: 77,
    13: 90,
    14: -1,  # DK/Refused/Missing -> null
}

BRFSS_2023_SOURCES: list[str] = [
    "https://www.cdc.gov/brfss/annual_data/2023/files/LLCP2023XPT.zip",
    "https://www.cdc.gov/brfss/annual_data/2023/zip/codebook23_llcp-v2-508.zip",
]


def decode_brfss_person(frame: pd.DataFrame, *, year: int) -> pd.DataFrame:
    """Decode a BRFSS raw dataframe into the v1 brfss_person schema."""
    require_columns(actual=frame.columns, required=list(RAW_COLUMNS), context="BRFSS decode")

    output = pd.DataFrame(index=frame.index)
    output["year"] = year

    state = pd.to_numeric(frame["_STATE"], errors="coerce")
    if state.isna().any():
        raise ValueError("BRFSS _STATE contains nulls; cannot build stable join keys.")
    output["state_fips"] = state.astype("Int64").astype(str).str.zfill(2)

    age_group = pd.to_numeric(frame["_AGEG5YR"], errors="coerce").astype("Int64")
    age_mid = age_group.map(AGE_MIDPOINT_BY_GROUP)
    output["age"] = age_mid.where(age_mid > 0).astype("Int64")

    bmi_raw = pd.to_numeric(frame["_BMI5"], errors="coerce")
    bmi = (bmi_raw.where(bmi_raw != 9999) / 100.0).astype("float64")
    bmi = bmi.where((bmi >= 10) & (bmi <= 60))
    output["bmi"] = bmi

    smoker_raw = pd.to_numeric(frame["_SMOKER3"], errors="coerce").astype("Int64")
    smoker = pd.Series(pd.NA, index=frame.index, dtype="boolean")
    smoker = smoker.mask(smoker_raw.isin([1, 2]), True)
    smoker = smoker.mask(smoker_raw.isin([3, 4]), False)
    output["smoker"] = smoker

    drinks_raw = pd.to_numeric(frame["_DRNKWK2"], errors="coerce")
    drinks = pd.Series(pd.NA, index=frame.index, dtype="Int64")
    drinks = drinks.mask(drinks_raw == 0, 0)
    valid = (drinks_raw.notna()) & (drinks_raw != 99900) & (drinks_raw != 0)
    derived = np.rint(drinks_raw.where(valid) / 100.0)
    drinks = drinks.mask(valid, derived.astype("Int64"))
    drinks = drinks.clip(lower=0, upper=70).astype("Int64")
    output["alcohol_servings_per_week"] = drinks

    exercise_raw = pd.to_numeric(frame["PA3MIN_"], errors="coerce")
    exercise = exercise_raw.where(exercise_raw <= 99999).clip(lower=0, upper=2000)
    exercise = pd.Series(np.rint(exercise), index=frame.index)
    output["exercise_minutes_per_week"] = exercise.astype("Int64")

    output["label_heart_disease"] = _decode_yes_no_blank(
        pd.to_numeric(frame["_MICHD"], errors="coerce")
    )
    output["label_chronic_lung_disease"] = _decode_yes_no_unknown(
        pd.to_numeric(frame["CHCCOPD3"], errors="coerce")
    )
    output["label_stroke"] = _decode_yes_no_unknown(
        pd.to_numeric(frame["CVDSTRK3"], errors="coerce")
    )
    output["label_depression"] = _decode_yes_no_unknown(
        pd.to_numeric(frame["ADDEPEV3"], errors="coerce")
    )
    output["label_diabetes"] = _decode_diabetes(pd.to_numeric(frame["DIABETE4"], errors="coerce"))

    output["survey_weight"] = pd.to_numeric(frame["_LLCPWT"], errors="coerce").astype("float64")

    return output


def _decode_yes_no_blank(values: pd.Series) -> pd.Series:
    """Decode 1->1, 2->0, else -> NA."""
    result = pd.Series(pd.NA, index=values.index, dtype="Int64")
    result = result.mask(values == 1, 1)
    result = result.mask(values == 2, 0)
    return result


def _decode_yes_no_unknown(values: pd.Series) -> pd.Series:
    """Decode 1->1, 2->0, (7/9/blank)->NA."""
    result = pd.Series(pd.NA, index=values.index, dtype="Int64")
    result = result.mask(values == 1, 1)
    result = result.mask(values == 2, 0)
    return result


def _decode_diabetes(values: pd.Series) -> pd.Series:
    """Decode DIABETE4 into a v1 binary label (1=yes, 0=no)."""
    result = pd.Series(pd.NA, index=values.index, dtype="Int64")
    result = result.mask(values == 1, 1)
    result = result.mask(values.isin([2, 3, 4]), 0)
    return result


def build_brfss_tables(
    *,
    base_dir: Path,
    years: list[int],
    force: bool,
    dry_run: bool,
) -> None:
    """Build processed BRFSS tables for the given year(s)."""
    paths = build_ingest_paths(base_dir)
    for year in years:
        if year != 2023:
            raise NotImplementedError(
                f"BRFSS build is pinned to 2023 for v1. Unsupported year: {year}."
            )

        raw_dir = paths.brfss_raw_dir(year)
        xpt_path = raw_dir / f"LLCP{year}.XPT"
        if not xpt_path.exists():
            raise FileNotFoundError(f"Missing raw XPT. Run download first: {xpt_path}")

        out_path = paths.brfss_person_parquet(year)
        out_dir = out_path.parent
        prov_path = paths.provenance_brfss_person(year)

        print(f"Build BRFSS person table: {xpt_path} -> {out_path}")
        if out_path.exists() and not force:
            print(f"Skip build (exists): {out_path}")
            continue
        if dry_run:
            write_provenance_json(
                prov_path,
                dataset_name="brfss_person",
                dataset_version=str(year),
                sources=BRFSS_2023_SOURCES,
                files=[],
                dry_run=True,
            )
            continue

        reader = pd.read_sas(xpt_path, format="xport", iterator=True, chunksize=50_000)
        out_dir.mkdir(parents=True, exist_ok=True)

        required_cols = [
            "year",
            "state_fips",
            "age",
            "bmi",
            "smoker",
            "alcohol_servings_per_week",
            "exercise_minutes_per_week",
            "label_heart_disease",
            "label_chronic_lung_disease",
            "label_stroke",
            "label_depression",
            "label_diabetes",
            "survey_weight",
        ]

        tmp_path = out_path.with_suffix(out_path.suffix + ".part")
        if tmp_path.exists():
            tmp_path.unlink()

        rows_written = 0
        null_counts = {name: 0 for name in required_cols}
        writer: pq.ParquetWriter | None = None
        try:
            for chunk in reader:
                chunk = chunk.loc[:, list(RAW_COLUMNS)]
                decoded_chunk = decode_brfss_person(chunk, year=year)
                table = pa.Table.from_pandas(decoded_chunk, preserve_index=False)
                if writer is None:
                    writer = pq.ParquetWriter(str(tmp_path), table.schema)
                writer.write_table(table)
                rows_written += len(decoded_chunk)
                for name in required_cols:
                    null_counts[name] += int(decoded_chunk[name].isna().sum())
        finally:
            if writer is not None:
                writer.close()

        if writer is None:  # pragma: no cover
            raise ValueError(f"No rows decoded from BRFSS XPT: {xpt_path}")

        tmp_path.replace(out_path)
        print(f"Rows written: {rows_written:,}")
        print(f"Null counts: {null_counts}")

        files: list[FileProvenance] = [
            collect_file_provenance(xpt_path, root=base_dir),
            collect_file_provenance(out_path, root=base_dir),
        ]
        write_provenance_json(
            prov_path,
            dataset_name="brfss_person",
            dataset_version=str(year),
            sources=BRFSS_2023_SOURCES,
            files=files,
            extra={"rows": rows_written, "null_counts": null_counts},
        )


def main(argv: list[str] | None = None) -> None:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description="Build processed BRFSS tables (v1).")
    add_common_pipeline_args(parser)
    args = parser.parse_args(argv)
    years = parse_years_from_args(args)
    build_brfss_tables(
        base_dir=Path(args.base_dir),
        years=years,
        force=bool(args.force),
        dry_run=bool(args.dry_run),
    )


if __name__ == "__main__":
    main()
