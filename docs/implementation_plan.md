# Baseline Implementation History

This document records the baseline architecture that existed before the independent product
roadmap. Current product planning lives in `docs/roadmap.md`, the source-of-truth feature tracker
lives in `docs/feature_status.md`, and active implementation prompts live under
`docs/superpowers/plans/`. The original `2026-04-30-longevity-lab-expansion.md` plan is historical
reference material, not a pending task list.

## Shipped baseline

The repo already includes:

- BRFSS and EPA raw/processed pipeline scripts.
- Integrated person-year table builder.
- DuckDB view builder.
- Hydra/Optuna training entrypoint for calibrated decision-tree bundles.
- Bundle evaluation summary CLI.
- Typed FastAPI API with metadata, scenario compare, lazy scenario explain, pipeline-status,
  evidence, model-card, geography-context, and community-context endpoints.
- React dashboard with Explorer, Data Evidence, Community Context, Model Cards, and Scenario Lab
  views.
- Playwright E2E smoke coverage.

## Original workstreams

The baseline can be understood through six workstreams:

1. Data ingest and provenance.
2. Feature and label design.
3. Modeling and evaluation.
4. Backend API and artifact loading.
5. Frontend scenario comparison and organ visualization.
6. Integration, validation, and documentation.

## Current delivered expansion

The independent-product expansion has since added:

- A public data-source registry.
- Expanded BRFSS and contextual feature contracts.
- Scripted EDA and model reports.
- Stronger calibrated tabular models with the promoted `real-20260508-xgboost-shap` artifact.
- Separate causal-inference workbench and Community Context surfacing.
- Versioned API contracts and richer UI pages.
- Deployment packaging for a public product prototype.
