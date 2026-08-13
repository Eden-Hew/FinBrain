$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
$node = "C:\Program Files\nodejs\node.exe"
$vite = Join-Path $repoRoot "frontend\node_modules\vite\bin\vite.js"
$runtimeDir = Join-Path $repoRoot ".runtime"
$pidFile = Join-Path $runtimeDir "demo-processes.json"

if (-not (Test-Path -LiteralPath $python)) { throw "Project virtual environment is missing." }
if (-not (Test-Path -LiteralPath $node)) { throw "Node.js is missing." }
if (-not (Test-Path -LiteralPath $vite)) { throw "Frontend Vite dependency is missing." }
if (-not (Test-Path -LiteralPath (Join-Path $repoRoot "backend\.env"))) { throw "backend/.env is missing." }
if (-not (Test-Path -LiteralPath (Join-Path $repoRoot "frontend\node_modules"))) { throw "Frontend dependencies are missing." }
if (Test-Path -LiteralPath $pidFile) { throw "A demo PID file already exists. Run scripts/stop_demo.ps1 first." }

$occupied = Get-NetTCPConnection -State Listen -LocalPort 8000,5173 -ErrorAction SilentlyContinue
if ($occupied) { throw "Port 8000 or 5173 is already in use." }

New-Item -ItemType Directory -Path $runtimeDir -Force | Out-Null

$backend = Start-Process -FilePath $python `
  -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000" `
  -WorkingDirectory (Join-Path $repoRoot "backend") -WindowStyle Hidden -PassThru
$frontend = Start-Process -FilePath $node `
  -ArgumentList "`"$vite`"", "--host", "127.0.0.1", "--port", "5173", "--strictPort" `
  -WorkingDirectory (Join-Path $repoRoot "frontend") -WindowStyle Hidden -PassThru
$telegram = Start-Process -FilePath $python `
  -ArgumentList "-m", "app.integrations.telegram.runner" `
  -WorkingDirectory (Join-Path $repoRoot "backend") -WindowStyle Hidden -PassThru

$processes = @(
  @{ name = "backend"; pid = $backend.Id; started = $backend.StartTime.ToString("O") },
  @{ name = "frontend"; pid = $frontend.Id; started = $frontend.StartTime.ToString("O") },
  @{ name = "telegram"; pid = $telegram.Id; started = $telegram.StartTime.ToString("O") }
)
$emailEnabled = Select-String `
  -LiteralPath (Join-Path $repoRoot "backend\.env") `
  -Pattern '^EMAIL_CONNECTOR_ENABLED\s*=\s*true\s*$' `
  -CaseSensitive:$false -Quiet
if ($emailEnabled) {
  $email = Start-Process -FilePath $python `
    -ArgumentList "-m", "app.integrations.email_connector.runner" `
    -WorkingDirectory (Join-Path $repoRoot "backend") -WindowStyle Hidden -PassThru
  $processes += @{
    name = "email"
    pid = $email.Id
    started = $email.StartTime.ToString("O")
  }
}
$processes | ConvertTo-Json | Set-Content -LiteralPath $pidFile -Encoding UTF8

$ready = $false
for ($attempt = 0; $attempt -lt 30; $attempt++) {
  try {
    $health = Invoke-RestMethod -Uri "http://127.0.0.1:8000/health" -TimeoutSec 2
    $page = Invoke-WebRequest -Uri "http://127.0.0.1:5173/" -UseBasicParsing -TimeoutSec 2
    if ($health.status -eq "ok" -and $page.StatusCode -eq 200) { $ready = $true; break }
  } catch {}
  Start-Sleep -Milliseconds 500
}

if (-not $ready) { throw "Demo processes started, but local health checks did not become ready." }
Write-Output "FinBrain frontend: http://127.0.0.1:5173"
Write-Output "FinBrain API docs: http://127.0.0.1:8000/docs"
Write-Output "Telegram worker started in polling mode."
if ($emailEnabled) { Write-Output "Email worker started in read-only polling mode." }
