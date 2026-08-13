$ErrorActionPreference = "Stop"

$health = Invoke-RestMethod -Uri "http://127.0.0.1:8000/health" -TimeoutSec 5
$telegram = Invoke-RestMethod -Uri "http://127.0.0.1:8000/integrations/telegram/status" -TimeoutSec 5
$frontend = Invoke-WebRequest -Uri "http://127.0.0.1:5173/" -UseBasicParsing -TimeoutSec 5

Write-Output "Backend: $($health.status) ($($health.database), $($health.mode))"
Write-Output "Frontend: HTTP $($frontend.StatusCode)"
Write-Output "Telegram: $($telegram.status) ($($telegram.mode))"
Write-Output "Detector ready: $($telegram.detector_ready)"
Write-Output "Last Telegram update: $($telegram.last_update_at)"
