# ErganiOS scheduled sync — every 10 minutes (:00, :10, :20, ...)
# Run as Administrator:
#   powershell -ExecutionPolicy Bypass -File scripts\setup_scheduled_sync_task.ps1

$ErrorActionPreference = "Stop"

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Python = Join-Path $Root "venv\Scripts\python.exe"
$Script = Join-Path $Root "scripts\run_scheduled_sync.py"
$TaskName = "ErganiOS-ScheduledSync10Min"

if (-not (Test-Path $Python)) {
    throw "venv python not found: $Python"
}
if (-not (Test-Path $Script)) {
    throw "script not found: $Script"
}

$TaskCmd = "`"$Python`" `"$Script`""

schtasks /create `
    /tn $TaskName `
    /tr $TaskCmd `
    /sc daily `
    /st 00:00 `
    /ri 10 `
    /du 24:00 `
    /ru SYSTEM `
    /f | Out-Null

Write-Host "OK task registered: $TaskName"
Write-Host "Command: $TaskCmd"
Write-Host "Dry-run: & `"$Python`" `"$Script`" --dry-run"
Write-Host "Run now: schtasks /run /tn $TaskName"
