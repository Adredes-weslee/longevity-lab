#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${script_dir}/.." && pwd)"
cd "${repo_root}"

groups=(dev train)
skip_frontend=0
run_checks=0

usage() {
  cat <<'EOF'
Usage: bash scripts/bootstrap_dev.sh [--explainability] [--notebook] [--skip-frontend] [--run-checks]

Installs Python dev/train and frontend dependencies from the checked-in lockfiles.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --explainability)
      groups+=(explainability)
      ;;
    --notebook)
      groups+=(notebook)
      ;;
    --skip-frontend)
      skip_frontend=1
      ;;
    --run-checks)
      run_checks=1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

if ! command -v pdm >/dev/null 2>&1; then
  echo "Missing required command: pdm" >&2
  echo "Install PDM first, for example: pipx install pdm" >&2
  exit 1
fi

if [[ "${skip_frontend}" -eq 0 ]] && ! command -v npm >/dev/null 2>&1; then
  echo "Missing required command: npm" >&2
  echo "Install Node.js 22+ with npm 10+ first." >&2
  exit 1
fi

pdm_args=(install)
for group in "${groups[@]}"; do
  pdm_args+=(-G "${group}")
done

echo "==> pdm ${pdm_args[*]}"
pdm "${pdm_args[@]}"

if [[ "${skip_frontend}" -eq 0 ]]; then
  pushd frontend >/dev/null
  if [[ -f package-lock.json ]]; then
    echo "==> npm ci"
    npm ci
  else
    echo "==> npm install"
    npm install
  fi
  popd >/dev/null
fi

if [[ "${run_checks}" -eq 1 ]]; then
  echo "==> bash scripts/check_all.sh"
  bash scripts/check_all.sh
fi

echo "Development bootstrap complete."
