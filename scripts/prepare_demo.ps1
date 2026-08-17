param(
  [switch]$SkipNetworkChecks,
  [switch]$SkipDetector,
  [switch]$SkipTests
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "demo_processes.ps1")
$pythonRuntime = Get-DemoPythonRuntime -RepoRoot $repoRoot
$envFile = Join-Path $repoRoot "backend\.env"
$frontendModules = Join-Path $repoRoot "frontend\node_modules"

foreach ($required in @($pythonRuntime.executable, $envFile, $frontendModules)) {
  if (-not (Test-Path -LiteralPath $required)) {
    throw "A required local dependency is missing. See README setup instructions."
  }
}
foreach ($name in @(
  "TOKEN_ROOT_SECRET",
  "TOKEN_HASH_SECRET",
  "VAULT_MASTER_KEY",
  "DATABASE_URL",
  "GEMINI_API_KEY"
)) {
  if (-not (Test-DemoEnvValue -EnvFile $envFile -Name $name)) {
    throw "$name is not configured in backend/.env."
  }
}
if (Get-NetTCPConnection -State Listen -LocalPort 8000,5173 -ErrorAction SilentlyContinue) {
  throw "Port 8000 or 5173 is in use. Stop the demo before preparation."
}

Push-Location (Join-Path $repoRoot "backend")
try {
  Write-Output "Python runtime: $($pythonRuntime.description)"
  if (-not $SkipDetector) {
    $arguments = @($pythonRuntime.arguments) + @("-m", "scripts.prewarm_detector")
    & $pythonRuntime.executable @arguments
    if ($LASTEXITCODE -ne 0) { throw "Detector prewarm failed." }
  }
  if (-not $SkipNetworkChecks) {
    $arguments = @($pythonRuntime.arguments) + @("-m", "scripts.check_gemini")
    & $pythonRuntime.executable @arguments
    if ($LASTEXITCODE -ne 0) { throw "Gemini connectivity check failed." }
    $arguments = @($pythonRuntime.arguments) + @("-m", "scripts.check_supabase")
    & $pythonRuntime.executable @arguments
    if ($LASTEXITCODE -ne 0) { throw "Supabase schema check failed." }
    if (Test-DemoEnvValue -EnvFile $envFile -Name "TELEGRAM_BOT_TOKEN") {
      $arguments = @($pythonRuntime.arguments) + @("-m", "scripts.check_telegram")
      & $pythonRuntime.executable @arguments
      if ($LASTEXITCODE -ne 0) { throw "Telegram connectivity check failed." }
    } else { Write-Output "Telegram: disabled; optional check skipped." }
    if (Test-DemoEnvFlag -EnvFile $envFile -Name "EMAIL_CONNECTOR_ENABLED") {
      $arguments = @($pythonRuntime.arguments) + @("-m", "scripts.check_email")
      & $pythonRuntime.executable @arguments
      if ($LASTEXITCODE -ne 0) { throw "Email connectivity check failed." }
    } else { Write-Output "Email: disabled; optional check skipped." }
    $arguments = @($pythonRuntime.arguments) + @("-m", "scripts.check_demo_data")
    & $pythonRuntime.executable @arguments
    if ($LASTEXITCODE -ne 0) { throw "Demo data verification failed." }
  }
  if (-not $SkipTests) {
    $arguments = @($pythonRuntime.devArguments) + @("-m", "pytest", "-q")
    & $pythonRuntime.executable @arguments
    if ($LASTEXITCODE -ne 0) { throw "Backend tests failed." }
    $arguments = @($pythonRuntime.devArguments) + @("-m", "ruff", "check", "app", "tests", "scripts")
    & $pythonRuntime.executable @arguments
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
