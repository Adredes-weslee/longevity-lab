# Contributing

## Start here

If you are new to the repo:

1. Run through `docs/quickstart.md`.
2. Confirm you can start the backend + frontend locally.
3. Run `.\scripts\check_all.ps1` or `bash scripts/check_all.sh`.
4. Pick a scoped task from `docs/feature_status.md`.

## Code style

- Use Python type hints on all public functions and methods.
- Use Google-style docstrings for non-trivial modules, classes, and functions.
- Prefer small focused classes with clear responsibilities over deep inheritance.
- Prefer explicit service/domain objects over generic abstractions.

## Commit style

Use short imperative commit subjects with an area prefix.

Examples:

- `api: add scenario response schema`
- `frontend: wire organ inspector selection`
- `pipeline: add BRFSS ingest entrypoint`

Recommended format:

```text
area: imperative summary

Why this change is needed.
What tradeoff or behavior changed.
```

## Branching workflow

This repo is easiest to manage with a simple trunk-based flow.

### Required long-lived branches

- `main`: always runnable. Only merge via PR. Keep it green (tests/builds pass).

Optional (only if you feel you need it):

- `dev`: integration branch when you want to batch merges. PRs target `dev`, and `dev` is periodically merged into `main`.

### Short-lived branches (always)

Create a branch per work item:

- `feat/<area>/<short-desc>` (new feature)
- `fix/<area>/<short-desc>` (bugfix)
- `chore/<area>/<short-desc>` (tooling/cleanup)
- `docs/<short-desc>` (documentation only)
- `exp/<short-desc>` (experiments; can be force-pushed; do not depend on this staying stable)

Areas should match repo structure: `frontend`, `api`, `services`, `pipeline`, `docs`, `tests`.

### Release branches

Near public release checkpoints, cut a freeze branch from `main`:

- `release/<yyyy-mm-dd>-<milestone>`

Only allow critical fixes into release branches. Tag the final commit for that milestone.

### Merge policy

- Prefer **squash merge** for PRs (one clean commit per work item).
- Keep PRs small and update `docs/feature_status.md` when a feature moves between `TODO`/`STUB`/`DEMO`/`DONE`.

## Architecture guardrails

- Do not commit large raw datasets.
- Do not add a second backend framework or global state library without a documented reason.
- Keep React in charge of DOM rendering; use D3 for scales, geometry, and isolated imperative helpers.
- Keep preprocessing inside the training/inference pipeline to avoid leakage.

## Pre-commit hooks (recommended)

Install once per clone:

```powershell
pdm install -G dev
pdm run pre-commit install
```

Run on demand:

```powershell
pdm run pre-commit run --all-files
```

## Before you open a PR

- Prefer reproducible installs:
  - backend: `pdm install -G dev`
  - frontend: `cd frontend; npm ci`
- Run the one-command checks:
  - PowerShell: `.\scripts\check_all.ps1`
  - bash/zsh: `bash scripts/check_all.sh`
- If you changed the dashboard flow or frontend/backend contracts, also run:
  - `cd frontend; npm run test:e2e`
