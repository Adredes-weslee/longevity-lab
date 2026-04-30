param(
  [switch]$Fix
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ($Fix) {
  .\\scripts\\check_backend.ps1 -Fix
} else {
  .\\scripts\\check_backend.ps1
}
.\\scripts\\check_frontend.ps1
