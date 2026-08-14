$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "demo_processes.ps1")
$pidFile = Join-Path $repoRoot ".runtime\demo-processes.json"
if (-not (Test-Path -LiteralPath $pidFile)) {
  Write-Output "No FinBrain demo PID file was found."
  exit 0
}

$parsedEntries = Get-Content -LiteralPath $pidFile -Raw | ConvertFrom-Json
$entries = if ($parsedEntries -is [array]) { $parsedEntries } else { @($parsedEntries) }
[array]::Reverse($entries)
foreach ($entry in $entries) {
  Stop-DemoEntry -Entry $entry
}
Remove-Item -LiteralPath $pidFile -Force

for ($attempt = 0; $attempt -lt 10; $attempt++) {
  $listeners = @(Get-NetTCPConnection -State Listen -LocalPort 8000,5173 -ErrorAction SilentlyContinue)
  if (-not $listeners) { break }
  Start-Sleep -Milliseconds 250
}
if ($listeners) {
  throw "A process still owns demo port 8000 or 5173; it was not stopped without validated ownership."
}
Write-Output "FinBrain demo processes stopped; ports 8000 and 5173 are free."
