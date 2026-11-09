# Wrapper for Task Scheduler: daily pull of Microsoft Clarity summary (clarity_daily.py), read-only.
# Usage: powershell -NoProfile -File run_clarity_daily.ps1 [-Client Andverpersonalinjury] [-Label tilda]
# The Clarity API keeps only 3 days and allows 10 requests/day per project; this pull uses 4 requests.
# Token comes from the user environment variable LANDVER_CLARITY_API_TOKEN_TILDA (task runs as the same user).
# Events go to Scripts\_clarity_daily.log (rotated at 1 MB). ASCII-only on purpose (PowerShell 5.1).
param(
    [string]$Client = 'Andverpersonalinjury',
    [string]$Label  = 'tilda'
)

$python = 'D:\Programs\Python\python.exe'
$root   = $PSScriptRoot
$log    = Join-Path $root '_clarity_daily.log'

Set-Location $root
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUTF8 = '1'

function Write-Log([string]$msg) {
    try {
        if ((Test-Path $log) -and ((Get-Item $log).Length -gt 1MB)) { Move-Item -Force $log "$log.old" }
        Add-Content -Path $log -Value ("[{0}] {1}" -f (Get-Date -Format 's'), $msg) -ErrorAction Stop
    } catch { }
}

Write-Log "start $Client/$Label"
$out = & $python 'clarity_daily.py' '--client-folder' $Client '--label' $Label 2>&1 | Out-String
$code = $LASTEXITCODE
Write-Log ("exit {0}: {1}" -f $code, ($out.Trim() -replace "\r?\n", ' | '))
exit $code
