# Baseline Implementation History

This document records the baseline architecture that existed before the independent product roadmap. Current product planning lives in `docs/roadmap.md` and implementation PR prompts live in `docs/superpowers/plans/2026-04-30-longevity-lab-expansion.md`.

## Shipped baseline

The repo already includes:

- BRFSS and EPA raw/processed pipeline scripts.
- Integrated person-year table builder.
- DuckDB view builder.
- Hydra/Optuna training entrypoint for calibrated decision-tree bundles.
- Bundle evaluation summary CLI.
- Typed FastAPI API with metadata, scenario compare, and pipeline-status endpoints.
- React dashboard with Explorer and Data integration views.
- Playwright E2E smoke coverage.

## Original workstreams

The baseline can be understood through six workstreams:

1. Data ingest and provenance.
2. Feature and label design.
3. Modeling and evaluation.
4. Backend API and artifact loading.
5. Frontend scenario comparison and organ visualization.
6. Integration, validation, and documentation.

## Current direction

The next phase moves beyond the baseline by adding:

- A public data-source registry.
- Expanded BRFSS and contextual feature contracts.
- Scripted EDA and model reports.
- Stronger calibrated tabular models.
- Separate causal-inference workbench.
- Versioned API contracts and richer UI pages.
- Deployment packaging for a public product prototype.
