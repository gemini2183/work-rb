# Stops ONLY the guard process (gads_spend_guard_cpa.py --client <Client>) so that run_guard.ps1 restarts it.
# Used to restart a guard after a code/config change and to test the autostart wrapper. Does not touch other processes.
# Usage: powershell -File stop_guard.ps1 -Client ProfiMet|EkspertAgro
# ASCII-only on purpose (PowerShell 5.1).
param(
    [Parameter(Mandatory = $true)][ValidateSet('ProfiMet', 'EkspertAgro')][string]$Client
)
$procs = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -like '*gads_spend_guard_cpa.py*' -and $_.CommandLine -match "--client\s+$Client(\s|$)" }
if (-not $procs) { Write-Output "no guard process for $Client"; exit 0 }
foreach ($p in $procs) {
    Write-Output ("stopping PID {0} (started {1})" -f $p.ProcessId, $p.CreationDate.ToString('s'))
    Stop-Process -Id $p.ProcessId -Force
}
