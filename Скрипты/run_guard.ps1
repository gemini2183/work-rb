# Wrapper for Task Scheduler: keeps gads_spend_guard_cpa.py alive for one client (ProfiMet | EkspertAgro).
# Usage: powershell -File run_guard.ps1 -Client ProfiMet
# - if a guard process for this client already runs (started by hand or by an old session), it is NOT duplicated:
#   the wrapper only watches it and takes over when it disappears (the script has no single-instance lock);
# - if the process exits (any code; it is meant to run forever), restart after a pause; a quick death
#   (lived < 2 min) doubles the pause: 60, 120, 240, 480, 600 s, so a start-up failure does not spam Telegram;
# - all output goes to Scripts\_guard_*.out (same files as before), rotated at 5 MB on restart.
# ASCII-only on purpose: PowerShell 5.1 breaks on non-BOM UTF-8 literals. Paths come from $PSScriptRoot.
param(
    [Parameter(Mandatory = $true)][ValidateSet('ProfiMet', 'EkspertAgro')][string]$Client,
    [int]$StartDelaySec = 60
)

$python = 'D:\Programs\Python\python.exe'
$root   = $PSScriptRoot
$script = 'gads_spend_guard_cpa.py'
$outMap = @{ 'ProfiMet' = '_guard_profimet.out'; 'EkspertAgro' = '_guard_ea.out' }
$out    = Join-Path $root $outMap[$Client]

Set-Location $root
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUTF8 = '1'

function Write-Log([string]$msg) {
    Add-Content -Path $out -Value ("[{0}] wrapper: {1}" -f (Get-Date -Format 's'), $msg)
}

function Get-GuardProcess {
    Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
        Where-Object { $_.CommandLine -like "*$script*" -and $_.CommandLine -match "--client\s+$Client(\s|$)" }
}

Write-Log "task started, waiting $StartDelaySec s for network"
Start-Sleep -Seconds $StartDelaySec

$pause = 60
$watching = $false
while ($true) {
    $existing = Get-GuardProcess
    if ($existing) {
        if (-not $watching) {
            Write-Log ("guard already running (PID {0}), watching, not starting a second one" -f (($existing | ForEach-Object { $_.ProcessId }) -join ','))
            $watching = $true
        }
        Start-Sleep -Seconds 30
        continue
    }
    if ($watching) { Write-Log "watched guard disappeared, taking over"; $watching = $false }

    if ((Test-Path $out) -and ((Get-Item $out).Length -gt 5MB)) { Move-Item -Force $out "$out.old" }
    Write-Log "--- start $script --client $Client --execute --telegram"
    $t0 = Get-Date
    # cmd handles redirection, so Python's UTF-8 output is written to the log as is
    & cmd.exe /c "`"$python`" -u $script --client $Client --execute --telegram >> `"$out`" 2>&1"
    $code = $LASTEXITCODE
    $lived = [int]((Get-Date) - $t0).TotalSeconds
    if ($lived -lt 120) { $pause = [Math]::Min($pause * 2, 600) } else { $pause = 60 }
    Write-Log ("--- exited with code {0} after {1} s, restart in {2} s" -f $code, $lived, $pause)
    Start-Sleep -Seconds $pause
}
