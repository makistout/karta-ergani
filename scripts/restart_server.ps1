# Επανεκκίνηση Flask (karta-ergani) — port 5051
$ErrorActionPreference = "SilentlyContinue"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$p = Get-NetTCPConnection -LocalPort 5051 -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -Unique
if ($p) {
    $p | ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }
}
Start-Sleep -Seconds 2
$env:PYTHONIOENCODING = "utf-8"
python run.py
