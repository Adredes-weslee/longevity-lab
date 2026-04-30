param(
  [switch]$Fix
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Invoke-NativeStep {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Label,
    [Parameter(Mandatory = $true)]
    [scriptblock]$Action
  )

  & $Action
  if ($LASTEXITCODE -ne 0) {
    throw "$Label failed (exit code $LASTEXITCODE)."
  }
}

if (-not (Get-Command "pdm" -ErrorAction SilentlyContinue)) {
  Write-Host "Missing PDM. Install it first (recommended via pipx):" -ForegroundColor Yellow
  Write-Host "  pipx install pdm" -ForegroundColor Yellow
  Write-Host "Then install dependencies:" -ForegroundColor Yellow
  Write-Host "  pdm install -G dev" -ForegroundColor Yellow
  exit 1
}

if ($Fix) {
  Invoke-NativeStep "ruff check --fix" { pdm run ruff check src tests --fix }
  Invoke-NativeStep "ruff format" { pdm run ruff format src tests }
} else {
  Invoke-NativeStep "ruff check" { pdm run ruff check src tests }
  Invoke-NativeStep "ruff format --check" { pdm run ruff format --check src tests }
}
Invoke-NativeStep "mypy" { pdm run python -m mypy src tests }
Invoke-NativeStep "pytest" { pdm run python -m pytest }
