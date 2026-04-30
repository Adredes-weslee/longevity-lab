#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${script_dir}/.." && pwd)"
cd "${repo_root}"

fix="${1:-}"

if [[ "${fix}" == "--fix" ]]; then
  bash scripts/check_backend.sh --fix
else
  bash scripts/check_backend.sh
fi

bash scripts/check_frontend.sh
