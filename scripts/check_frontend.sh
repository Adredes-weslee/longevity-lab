#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${script_dir}/.." && pwd)"
cd "${repo_root}/frontend"

if [[ ! -d "node_modules" ]]; then
  if [[ -f "package-lock.json" ]]; then
    npm ci
  else
    npm install
  fi
fi

npm run check
npm run lint
npm run build
