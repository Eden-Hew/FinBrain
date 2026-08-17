$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "demo_processes.ps1")
$uvCommand = Get-Command uv -ErrorAction SilentlyContinue
if (-not $uvCommand) {
  throw "Required demo dependency is missing: uv is not installed or not on PATH."
}
$uv = $uvCommand.Source
$node = "C:\Program Files\nodejs\node.exe"
$vite = Join-Path $repoRoot "frontend\node_modules\vite\bin\vite.js"
$envFile = Join-Path $repoRoot "backend\.env"
$runtimeDir = Join-Path $repoRoot ".runtime"
$logDir = Join-Path $runtimeDir "logs"
$pidFile = Join-Path $runtimeDir "demo-processes.json"

foreach ($required in @($uv, $node, $vite, $envFile)) {
  if (-not (Test-Path -LiteralPath $required)) { throw "Required demo dependency is missing: $required" }
}
$listeners = @(Get-NetTCPConnection -State Listen -LocalPort 8000,5173 -ErrorAction SilentlyContinue)
if (Test-Path -LiteralPath $pidFile) {
  $parsedEntries = Get-Content -LiteralPath $pidFile -Raw | ConvertFrom-Json
  $existingEntries = if ($parsedEntries -is [array]) { $parsedEntries } else { @($parsedEntries) }
  $liveEntries = @($existingEntries | Where-Object { Get-DemoValidatedProcess -Entry $_ })
  if ($liveEntries -or $listeners) {
    throw "A tracked demo process or demo port is still active. Run scripts/stop_demo.ps1 first."
  }
  Remove-Item -LiteralPath $pidFile -Force
  Write-Output "Removed a stale FinBrain demo PID file."
}
if ($listeners) {
  throw "Port 8000 or 5173 is already in use."
}

New-Item -ItemType Directory -Path $logDir -Force | Out-Null
$processes = @()

function Save-DemoProcesses {
  $processes | ConvertTo-Json | Set-Content -LiteralPath $pidFile -Encoding UTF8
}

function ConvertTo-DemoCmdArgument {
  param([Parameter(Mandatory)][string]$Value)
  if ($Value -match '["\r\n]') { throw "A demo process argument contains unsupported characters." }
  return '"' + $Value.Replace('%', '%%') + '"'
}

function Start-DemoComponent {
  param(
    [Parameter(Mandatory)][string]$Name,
    [Parameter(Mandatory)][string]$Executable,
    [Parameter(Mandatory)][string[]]$Arguments,
    [Parameter(Mandatory)][string]$WorkingDirectory,
    [bool]$Required = $false
  )
  $stdout = Join-Path $logDir "$Name.stdout.log"
  $stderr = Join-Path $logDir "$Name.stderr.log"
  $launcher = Join-Path $runtimeDir "$Name.launch.cmd"
  $command = @($Executable) + $Arguments |
    ForEach-Object { ConvertTo-DemoCmdArgument -Value $_ }
  $commandLine = ($command -join ' ') +
    " <NUL 1>$(ConvertTo-DemoCmdArgument -Value $stdout)" +
    " 2>$(ConvertTo-DemoCmdArgument -Value $stderr)"
  @("@echo off", $commandLine) | Set-Content -LiteralPath $launcher -Encoding ASCII
  Write-Output "Starting FinBrain $Name..."
  $process = Start-Process -FilePath $env:ComSpec `
    -ArgumentList "/d /s /c `"`"$launcher`"`"" `
    -WorkingDirectory $WorkingDirectory -WindowStyle Hidden -PassThru
  Start-Sleep -Milliseconds 150
  if ($process.HasExited) { throw "$Name exited during startup. Check .runtime/logs." }
  $script:processes += [pscustomobject]@{
    name = $Name
    pid = $process.Id
    started = $process.StartTime.ToString("O")
    executable = $process.Path
    required = $Required
  }
  Save-DemoProcesses
}

function Assert-DemoProcessesRunning {
  foreach ($entry in $script:processes) {
    if (-not (Get-DemoValidatedProcess -Entry $entry)) {
      throw "$($entry.name) exited during startup. Check .runtime/logs."
    }
  }
}

try {
  Start-DemoComponent -Name "backend" -Executable $uv `
    -Arguments @("run", "python", "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000") `
    -WorkingDirectory (Join-Path $repoRoot "backend") -Required $true
  Start-DemoComponent -Name "frontend" -Executable $node `
    -Arguments @($vite, "--host", "127.0.0.1", "--port", "5173", "--strictPort") `
    -WorkingDirectory (Join-Path $repoRoot "frontend") -Required $true

  $telegramEnabled = Test-DemoEnvValue -EnvFile $envFile -Name "TELEGRAM_BOT_TOKEN"
  if ($telegramEnabled) {
    Start-DemoComponent -Name "telegram" -Executable $uv `
      -Arguments @("run", "python", "-m", "app.integrations.telegram.runner") `
      -WorkingDirectory (Join-Path $repoRoot "backend")
  }
  $emailEnabled = Test-DemoEnvFlag -EnvFile $envFile -Name "EMAIL_CONNECTOR_ENABLED"
  if ($emailEnabled) {
    Start-DemoComponent -Name "email" -Executable $uv `
      -Arguments @("run", "python", "-m", "app.integrations.email_connector.runner") `
      -WorkingDirectory (Join-Path $repoRoot "backend")
  }

  Write-Output "Waiting for the backend and frontend health checks..."
  $ready = $false
  for ($attempt = 0; $attempt -lt 40; $attempt++) {
    Assert-DemoProcessesRunning
    try {
      $health = Invoke-RestMethod -Uri "http://127.0.0.1:8000/health" -TimeoutSec 2
      $page = Invoke-WebRequest -Uri "http://127.0.0.1:5173/" -UseBasicParsing -TimeoutSec 2
      if ($health.status -eq "ok" -and $page.StatusCode -eq 200) { $ready = $true; break }
    } catch {}
    Start-Sleep -Milliseconds 500
  }
  if (-not $ready) { throw "Required local services did not become ready. Check .runtime/logs." }
  foreach ($entry in @($processes | Where-Object { -not $_.required })) {
    if (-not (Get-DemoValidatedProcess -Entry $entry)) {
      throw "$($entry.name) was configured but exited during startup. Check .runtime/logs."
    }
  }
  if ($telegramEnabled -or $emailEnabled) {
    Write-Output "Verifying configured connector processes..."
    # Connector status endpoints require a signed-in user's JWT. The local
    # launcher therefore checks only the worker processes it created and
    # leaves application-level connector status to the authenticated UI.
    for ($attempt = 0; $attempt -lt 8; $attempt++) {
      Start-Sleep -Milliseconds 250
      Assert-DemoProcessesRunning
    }
  }

  Write-Output "FinBrain frontend: http://127.0.0.1:5173"
  Write-Output "FinBrain API docs: http://127.0.0.1:8000/docs"
  Write-Output "Telegram worker: $(if ($telegramEnabled) { 'started' } else { 'disabled' })"
  Write-Output "Email worker: $(if ($emailEnabled) { 'started' } else { 'disabled' })"
} catch {
  $cleanupEntries = [object[]]$processes.Clone()
  [array]::Reverse($cleanupEntries)
  foreach ($entry in $cleanupEntries) {
    try { Stop-DemoEntry -Entry $entry } catch { Write-Warning $_.Exception.Message }
  }
  if (Test-Path -LiteralPath $pidFile) { Remove-Item -LiteralPath $pidFile -Force }
  throw
}
