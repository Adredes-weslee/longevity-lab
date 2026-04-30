# Git workflow

This repo uses small PRs against `main`, with isolated local worktrees for implementation branches.

## Branches

### `main`

- Keep `main` runnable.
- Merge through GitHub pull requests.
- Do not require protected-branch rules locally, but do not treat a branch as ready until checks and review converge.

### Implementation branches

Use a branch per PR-sized work item:

- `codex/pr-01-artifact-first-runtime`
- `codex/pr-02-data-source-registry`
- `codex/pr-03-brfss-v2-features`

Create branches in project-local worktrees under `.worktrees/<branch-slug>`. The `.worktrees/` path is ignored so worktree contents cannot be accidentally committed.

## Pull requests

Every PR should:

- Match one scoped item from `docs/superpowers/plans/2026-04-30-longevity-lab-expansion.md`.
- Update `docs/feature_status.md` when feature state changes.
- Update `README.md`, `docs/quickstart.md`, `docs/schema_contracts.md`, or `docs/data_dictionary.md` when setup, contracts, or data semantics change.
- Add or update tests when API contracts, data contracts, model outputs, or user-visible flows change.
- List checks run and any skipped checks with the exact reason.

## Ready-to-merge gate

A PR is ready only when:

- Targeted local checks pass.
- Broader checks pass when the touched surface warrants them.
- Local adversarial review finds no new P0, P1, or P2 issues against the latest commit hash.
- The PR description states data/artifact implications and any known limitations.

## Conflict avoidance

- Keep touch sets small.
- Do not reformat unrelated files.
- Land shared contracts before downstream frontend or pipeline work.
- Do not mix data-source ingestion, model changes, and UI redesign in one PR unless the roadmap explicitly combines them.
