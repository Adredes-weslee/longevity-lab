param(
  [switch]$Explainability,
  [switch]$Notebook,
  [switch]$SkipFrontend,
  [switch]$RunChecks
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

  Write-Host "==> $Label" -ForegroundColor Cyan
  & $Action
  if ($LASTEXITCODE -ne 0) {
    throw "$Label failed (exit code $LASTEXITCODE)."
  }
}

function Require-Command {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Name,
    [Parameter(Mandatory = $true)]
    [string]$InstallHint
  )

  if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
    Write-Host "Missing required command: $Name" -ForegroundColor Yellow
    Write-Host $InstallHint -ForegroundColor Yellow
    exit 1
  }
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Resolve-Path (Join-Path $scriptDir "..")
Set-Location $repoRoot

Require-Command "pdm" "Install PDM first, for example: pipx install pdm"
if (-not $SkipFrontend) {
  Require-Command "npm" "Install Node.js 22+ with npm 10+ first."
}

$npmCmd = Get-Command "npm.cmd" -ErrorAction SilentlyContinue
$npm = if ($null -ne $npmCmd) { $npmCmd.Source } else { "npm" }

$groups = @("dev", "train")
if ($Explainability) {
  $groups += "explainability"
}
if ($Notebook) {
  $groups += "notebook"
}

$pdmArgs = @("install")
foreach ($group in $groups) {
  $pdmArgs += @("-G", $group)
}
Invoke-NativeStep "pdm $($pdmArgs -join ' ')" { pdm @pdmArgs }

if (-not $SkipFrontend) {
  Push-Location "frontend"
  try {
    if (Test-Path "package-lock.json") {
      Invoke-NativeStep "npm ci" { & $npm ci }
    } else {
      Invoke-NativeStep "npm install" { & $npm install }
    }
  } finally {
    Pop-Location
  }
}

if ($RunChecks) {
  Invoke-NativeStep "scripts/check_all.ps1" { .\scripts\check_all.ps1 }
}

Write-Host "Development bootstrap complete." -ForegroundColor Green
