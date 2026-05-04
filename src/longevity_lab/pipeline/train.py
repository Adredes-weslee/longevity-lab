"""Hydra entrypoint for bundle training."""

from __future__ import annotations

from typing import Any, cast

import hydra  # type: ignore[import-untyped]
from omegaconf import DictConfig, OmegaConf  # type: ignore[import-untyped]

from longevity_lab.config_files import config_dir_path
from longevity_lab.pipeline.modeling import build_training_spec, train_bundle

CONFIG_PATH = str(config_dir_path())


@hydra.main(version_base="1.3", config_path=CONFIG_PATH, config_name="train")
def main(cfg: DictConfig) -> None:
    """Train a calibrated artifact bundle from the integrated person-year table."""
    raw_cfg = OmegaConf.to_container(cfg, resolve=True)
    if not isinstance(raw_cfg, dict):
        raise TypeError("Hydra train config must resolve to a mapping.")
    spec = build_training_spec(cast(dict[str, Any], raw_cfg))
    result = train_bundle(spec)
    print(f"Bundle written: {result.bundle_dir}")
    print(f"Manifest: {result.manifest_path}")
    print(f"Summary: {result.training_summary_path}")


if __name__ == "__main__":
    main()
