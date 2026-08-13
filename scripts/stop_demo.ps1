$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$pidFile = Join-Path $repoRoot ".runtime\demo-processes.json"
if (-not (Test-Path -LiteralPath $pidFile)) {
  Write-Output "No FinBrain demo PID file was found."
  exit 0
}

$entries = Get-Content -LiteralPath $pidFile -Raw | ConvertFrom-Json
foreach ($entry in $entries) {
  $process = Get-Process -Id $entry.pid -ErrorAction SilentlyContinue
  if (-not $process) { continue }
  $expected = [datetime]::Parse($entry.started)
  if ([math]::Abs(($process.StartTime - $expected).TotalSeconds) -gt 2) {
    Write-Warning "Skipped PID $($entry.pid) because it was reused by another process."
    continue
  }
  Stop-Process -Id $process.Id
  $process.WaitForExit(5000) | Out-Null
}
Remove-Item -LiteralPath $pidFile -Force
Write-Output "FinBrain demo processes stopped."
