# ErganiOS scheduled sync — every 15 minutes (:00, :15, :30, :45)
# Run as Administrator:
#   powershell -ExecutionPolicy Bypass -File scripts\setup_scheduled_sync_task.ps1

$ErrorActionPreference = "Stop"

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Python = Join-Path $Root "venv\Scripts\python.exe"
$Script = Join-Path $Root "scripts\run_scheduled_sync.py"
$TaskName = "ErganiOS-ScheduledSync15Min"
$LegacyTaskName = "ErganiOS-ScheduledSync10Min"

if (-not (Test-Path $Python)) {
    throw "venv python not found: $Python"
}
if (-not (Test-Path $Script)) {
    throw "script not found: $Script"
}

$TaskCmd = "`"$Python`" `"$Script`""

# Αφαίρεση παλιού task 10 λεπτών (αν υπάρχει)
schtasks /query /tn $LegacyTaskName 2>$null | Out-Null
if ($LASTEXITCODE -eq 0) {
    schtasks /delete /tn $LegacyTaskName /f | Out-Null
    Write-Host "Removed legacy task: $LegacyTaskName"
}

schtasks /create `
    /tn $TaskName `
    /tr $TaskCmd `
    /sc daily `
    /st 00:00 `
    /ri 15 `
    /du 24:00 `
    /ru SYSTEM `
    /f | Out-Null

Write-Host "OK task registered: $TaskName"
Write-Host "Command: $TaskCmd"
Write-Host "Dry-run: & `"$Python`" `"$Script`" --dry-run"
Write-Host "Run now: schtasks /run /tn $TaskName"
