<#
.SYNOPSIS
  Prepare / deploy FE+BE to Azure App Service at the local mapping-parity commit.

.DESCRIPTION
  Local HEAD (feature/wave3-parser-no-autodetect) includes caption UI, sibling FQN
  compose, discover warehouse_id, and bare-name fallback removal. Azure was on an
  older FE (subtitle "federated • N cols" only).

  Claims Overview.twbx variants on disk (same filename, different bytes):
    BF3F73A7...  28683 bytes  — live Databricks, Auto-Upload (0)
    BF77A8E0... 219424 bytes  — hyper extract, Auto-Upload (1)

  Usage:
    # Build zip artifacts only
    .\scripts\redeploy-azure-parity.ps1

    # Zip-deploy (requires Azure CLI logged in)
    .\scripts\redeploy-azure-parity.ps1 -Deploy `
      -ResourceGroup <rg> -ApiAppName <api-app> -UiAppName <ui-app> `
      -ApiBaseUrl https://<api-app>.azurewebsites.net/api/v1
#>
param(
  [switch]$Deploy,
  [string]$ResourceGroup = "",
  [string]$ApiAppName = "",
  [string]$UiAppName = "",
  [string]$ApiBaseUrl = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$sha = (git rev-parse HEAD).Trim()
$branch = (git rev-parse --abbrev-ref HEAD).Trim()
Write-Host "Parity deploy from $branch @ $sha"

$out = Join-Path $Root "deploy-artifacts"
New-Item -ItemType Directory -Force -Path $out | Out-Null

# --- Backend zip: src/ + requirements.txt ---
$apiZip = Join-Path $out "api-deploy.zip"
if (Test-Path $apiZip) { Remove-Item $apiZip -Force }
$apiStage = Join-Path $out "api-stage"
if (Test-Path $apiStage) { Remove-Item $apiStage -Recurse -Force }
New-Item -ItemType Directory -Force -Path $apiStage | Out-Null
Copy-Item -Recurse (Join-Path $Root "src") (Join-Path $apiStage "src")
Copy-Item (Join-Path $Root "requirements.txt") $apiStage
Compress-Archive -Path (Join-Path $apiStage "*") -DestinationPath $apiZip -Force
Write-Host "Wrote $apiZip"

# --- Frontend: ensure production API URL then build ---
$fe = Join-Path $Root "frontend"
if (-not $ApiBaseUrl) {
  Write-Host "WARNING: -ApiBaseUrl not set. Set NEXT_PUBLIC_API_BASE_URL before Azure build."
} else {
  @"
NEXT_PUBLIC_API_BASE_URL=$ApiBaseUrl
"@ | Set-Content -Encoding utf8 (Join-Path $fe ".env.production")
  Write-Host "Wrote frontend/.env.production -> $ApiBaseUrl"
}

Push-Location $fe
try {
  if (Test-Path ".next") { Remove-Item -Recurse -Force ".next" }
  if (Test-Path "node_modules") {
    npm run build
  } else {
    npm ci
    npm run build
  }
} finally {
  Pop-Location
}

$uiZip = Join-Path $out "frontend-deploy.zip"
if (Test-Path $uiZip) { Remove-Item $uiZip -Force }
# Zip frontend contents (wwwroot = frontend/)
Push-Location $fe
try {
  Compress-Archive -Path * -DestinationPath $uiZip -Force
} finally {
  Pop-Location
}
Write-Host "Wrote $uiZip"

"commit=$sha" | Set-Content -Encoding utf8 (Join-Path $out "PARITY_COMMIT.txt")
"branch=$branch" | Add-Content -Encoding utf8 (Join-Path $out "PARITY_COMMIT.txt")

if (-not $Deploy) {
  Write-Host ""
  Write-Host "Artifacts ready under deploy-artifacts/."
  Write-Host "To deploy with Azure CLI:"
  Write-Host "  .\scripts\redeploy-azure-parity.ps1 -Deploy -ResourceGroup <rg> -ApiAppName <api> -UiAppName <ui> -ApiBaseUrl https://<api>.azurewebsites.net/api/v1"
  Write-Host "Or VS Code: Deploy to Web App on api zip / frontend folder."
  exit 0
}

if (-not (Get-Command az -ErrorAction SilentlyContinue)) {
  throw "Azure CLI (az) not found. Install az, run 'az login', then re-run with -Deploy."
}
if (-not $ResourceGroup -or -not $ApiAppName -or -not $UiAppName) {
  throw "Deploy requires -ResourceGroup, -ApiAppName, and -UiAppName."
}

Write-Host "Deploying API -> $ApiAppName ..."
az webapp deploy --resource-group $ResourceGroup --name $ApiAppName --src-path $apiZip --type zip
Write-Host "Deploying UI -> $UiAppName ..."
az webapp deploy --resource-group $ResourceGroup --name $UiAppName --src-path $uiZip --type zip
Write-Host "Done. Smoke-test mapping on Claims Overview with identical file hash on both envs."
