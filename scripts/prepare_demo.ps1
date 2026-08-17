param(
  [switch]$SkipNetworkChecks,
  [switch]$SkipDetector,
  [switch]$SkipTests
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "demo_processes.ps1")
$uvCommand = Get-Command uv -ErrorAction SilentlyContinue
if (-not $uvCommand) {
  throw "A required local dependency is missing: uv is not installed or not on PATH."
}
$uv = $uvCommand.Source
$envFile = Join-Path $repoRoot "backend\.env"
$frontendModules = Join-Path $repoRoot "frontend\node_modules"

foreach ($required in @($uv, $envFile, $frontendModules)) {
  if (-not (Test-Path -LiteralPath $required)) {
    throw "A required local dependency is missing. See README setup instructions."
  }
}
foreach ($name in @("TOKEN_ROOT_SECRET", "DATABASE_URL", "GEMINI_API_KEY")) {
  if (-not (Test-DemoEnvValue -EnvFile $envFile -Name $name)) {
    throw "$name is not configured in backend/.env."
  }
}
if (Get-NetTCPConnection -State Listen -LocalPort 8000,5173 -ErrorAction SilentlyContinue) {
  throw "Port 8000 or 5173 is in use. Stop the demo before preparation."
}

Push-Location (Join-Path $repoRoot "backend")
try {
  if (-not $SkipDetector) {
    & $uv run python -m scripts.prewarm_detector
    if ($LASTEXITCODE -ne 0) { throw "Detector prewarm failed." }
  }
  if (-not $SkipNetworkChecks) {
    & $uv run python -m scripts.check_gemini
    if ($LASTEXITCODE -ne 0) { throw "Gemini connectivity check failed." }
    & $uv run python -m scripts.check_supabase
    if ($LASTEXITCODE -ne 0) { throw "Supabase schema check failed." }
    if (Test-DemoEnvValue -EnvFile $envFile -Name "TELEGRAM_BOT_TOKEN") {
      & $uv run python -m scripts.check_telegram
      if ($LASTEXITCODE -ne 0) { throw "Telegram connectivity check failed." }
    } else { Write-Output "Telegram: disabled; optional check skipped." }
    if (Test-DemoEnvFlag -EnvFile $envFile -Name "EMAIL_CONNECTOR_ENABLED") {
      & $uv run python -m scripts.check_email
      if ($LASTEXITCODE -ne 0) { throw "Email connectivity check failed." }
    } else { Write-Output "Email: disabled; optional check skipped." }
    & $uv run python -m scripts.check_demo_data
    if ($LASTEXITCODE -ne 0) { throw "Demo data verification failed." }
  }
  if (-not $SkipTests) {
    & $uv run --extra dev python -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw "Backend tests failed." }
    & $uv run --extra dev ruff check app tests scripts
    if ($LASTEXITCODE -ne 0) { throw "Backend lint failed." }
  }
} finally {
  Pop-Location
}

if (-not $SkipTests) {
  Push-Location (Join-Path $repoRoot "frontend")
  try {
    & npm.cmd run lint
    if ($LASTEXITCODE -ne 0) { throw "Frontend lint failed." }
    & npm.cmd run build
    if ($LASTEXITCODE -ne 0) { throw "Frontend build failed." }
  } finally {
    Pop-Location
  }
}

Write-Output "FinBrain demo preparation passed. No database reset was performed."
Write-Output "Use the explicit seed reset command from README only when you intend to replace demo data."
