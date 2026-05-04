"""Hydra entrypoint for bundle evaluation summaries."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import hydra  # type: ignore[import-untyped]
from omegaconf import DictConfig, OmegaConf  # type: ignore[import-untyped]

from longevity_lab.artifacts.store import ArtifactStore
from longevity_lab.config_files import config_dir_path
from longevity_lab.pipeline.modeling import evaluate_bundle, evaluate_bundle_slices

CONFIG_PATH = str(config_dir_path())


@hydra.main(version_base="1.3", config_path=CONFIG_PATH, config_name="evaluate")
def main(cfg: DictConfig) -> None:
    """Summarize per-condition metrics for a trained bundle."""
    raw_cfg = OmegaConf.to_container(cfg, resolve=True)
    if not isinstance(raw_cfg, dict):
        raise TypeError("Hydra evaluate config must resolve to a mapping.")
    artifacts_cfg = cast(dict[str, Any], raw_cfg)["artifacts"]
    evaluation_cfg = cast(dict[str, Any], raw_cfg)["evaluation"]
    store = ArtifactStore(Path(str(artifacts_cfg["base_dir"])))
    bundle = store.resolve(
        bundle_id=str(artifacts_cfg["bundle_id"]) if artifacts_cfg.get("bundle_id") else None
    )
    summary = evaluate_bundle(bundle.path)
    slice_summary = evaluate_bundle_slices(
        bundle.path,
        min_rows=int(evaluation_cfg["min_slice_rows"]),
    )
    print(summary.to_string(index=False))
    if not slice_summary.empty:
        print()
        print("Slice metrics preview:")
        preview = slice_summary.loc[slice_summary["status"] == "ok"].head(20)
        print(preview.to_string(index=False) if not preview.empty else "No evaluable slices.")
    output_path = artifacts_cfg.get("output_path")
    if output_path:
        path = Path(str(output_path))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(summary.to_dict(orient="records"), indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"Wrote evaluation summary: {path}")
    slice_output_path = artifacts_cfg.get("slice_output_path")
    if slice_output_path:
        path = Path(str(slice_output_path))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(slice_summary.to_dict(orient="records"), indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"Wrote slice summary: {path}")


if __name__ == "__main__":
    main()
