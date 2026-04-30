#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${script_dir}/.." && pwd)"
cd "${repo_root}"

fix="${1:-}"

if ! command -v pdm >/dev/null 2>&1; then
  echo "Missing PDM. Install it first (recommended via pipx):" >&2
  echo "  pipx install pdm" >&2
  echo "Then install dependencies:" >&2
  echo "  pdm install -G dev" >&2
  exit 1
fi

if [[ "${fix}" == "--fix" ]]; then
  pdm run ruff check src tests --fix
  pdm run ruff format src tests
else
  pdm run ruff check src tests
  pdm run ruff format --check src tests
fi

pdm run mypy src tests
pdm run pytest
