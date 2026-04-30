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

$npmCmd = (Get-Command "npm.cmd" -ErrorAction SilentlyContinue)
$npm = if ($null -ne $npmCmd) { $npmCmd.Source } else { "npm" }

Push-Location "frontend"
try {
  if (-not (Test-Path "node_modules")) {
    if (Test-Path "package-lock.json") {
      Invoke-NativeStep "npm ci" { & $npm ci }
    } else {
      Invoke-NativeStep "npm install" { & $npm install }
    }
  }
  Invoke-NativeStep "npm run check" { & $npm run check }
  Invoke-NativeStep "npm run lint" { & $npm run lint }
  Invoke-NativeStep "npm run build" { & $npm run build }
} finally {
  Pop-Location
}
