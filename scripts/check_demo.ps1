$ErrorActionPreference = "Continue"
$failed = $false
$repoRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "demo_processes.ps1")
$envFile = Join-Path $repoRoot "backend\.env"
$pidFile = Join-Path $repoRoot ".runtime\demo-processes.json"
$entries = @()

if (Test-Path -LiteralPath $pidFile) {
  try {
    $parsedEntries = Get-Content -LiteralPath $pidFile -Raw | ConvertFrom-Json
    $entries = if ($parsedEntries -is [array]) { $parsedEntries } else { @($parsedEntries) }
  } catch {
    Write-Output "Process registry: invalid"
    $failed = $true
  }
}

function Get-TrackedDemoComponent {
  param([Parameter(Mandatory)][string]$Name)
  return @($entries | Where-Object { $_.name -eq $Name } | Select-Object -First 1)
}

try {
  $health = Invoke-RestMethod -Uri "http://127.0.0.1:8000/health" -TimeoutSec 5
  if ($health.status -ne "ok") { throw "unexpected backend status" }
  Write-Output "Backend: healthy ($($health.database), $($health.mode))"
} catch {
  Write-Output "Backend: unavailable"
  $failed = $true
}

try {
  $frontend = Invoke-WebRequest -Uri "http://127.0.0.1:5173/" -UseBasicParsing -TimeoutSec 5
  if ($frontend.StatusCode -ne 200) { throw "unexpected frontend status" }
  Write-Output "Frontend: healthy (HTTP $($frontend.StatusCode))"
} catch {
  Write-Output "Frontend: unavailable"
  $failed = $true
}

$telegramEnabled = Test-DemoEnvValue -EnvFile $envFile -Name "TELEGRAM_BOT_TOKEN"
if (-not $telegramEnabled) {
  Write-Output "Telegram worker: disabled (optional)"
} else {
  $telegramEntry = Get-TrackedDemoComponent -Name "telegram"
  if ($telegramEntry -and (Get-DemoValidatedProcess -Entry $telegramEntry)) {
    Write-Output "Telegram worker: running (tracked local process)"
  } else {
    Write-Output "Telegram worker: unavailable"
    $failed = $true
  }
}

$emailEnabled = Test-DemoEnvFlag -EnvFile $envFile -Name "EMAIL_CONNECTOR_ENABLED"
if (-not $emailEnabled) {
  Write-Output "Email worker: disabled (optional)"
} else {
  $emailEntry = Get-TrackedDemoComponent -Name "email"
  if ($emailEntry -and (Get-DemoValidatedProcess -Entry $emailEntry)) {
    Write-Output "Email worker: running (tracked local process)"
  } else {
    Write-Output "Email worker: unavailable"
    $failed = $true
  }
}

$rotationEnabled = Test-DemoEnvFlag -EnvFile $envFile -Name "VAULT_AUTO_ROTATION_ENABLED"
if (-not $rotationEnabled) {
  Write-Output "Vault rotation worker: disabled (optional)"
} else {
  $rotationEntry = Get-TrackedDemoComponent -Name "vault-rotation"
  if ($rotationEntry -and (Get-DemoValidatedProcess -Entry $rotationEntry)) {
    Write-Output "Vault rotation worker: running (tracked local process)"
  } else {
    Write-Output "Vault rotation worker: unavailable"
    $failed = $true
  }
}

if ($failed) { exit 1 }
