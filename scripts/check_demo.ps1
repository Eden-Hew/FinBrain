$ErrorActionPreference = "Continue"
$failed = $false

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

try {
  $telegram = Invoke-RestMethod -Uri "http://127.0.0.1:8000/integrations/telegram/status" -TimeoutSec 5
  if (-not $telegram.configured) {
    Write-Output "Telegram: disabled (optional)"
  } elseif ($telegram.status -notin @("healthy", "starting")) {
    Write-Output "Telegram: unhealthy ($($telegram.status))"
    $failed = $true
  } else {
    Write-Output "Telegram: $($telegram.status) ($($telegram.mode)); detector ready: $($telegram.detector_ready)"
  }
} catch { Write-Output "Telegram: status unavailable" }

try {
  $email = Invoke-RestMethod -Uri "http://127.0.0.1:8000/integrations/email/status" -TimeoutSec 5
  if (-not $email.configured) {
    Write-Output "Email: disabled (optional)"
  } elseif ($email.status -notin @("healthy", "idle", "syncing")) {
    Write-Output "Email: unhealthy ($($email.status))"
    $failed = $true
  } else {
    Write-Output "Email: $($email.status); last sync: $($email.last_sync_at)"
  }
} catch { Write-Output "Email: status unavailable" }

if ($failed) { exit 1 }
