<#
  Keep the review and report server running: start it at logon and start it again if it stops (Windows PowerShell, run by the scheduled task <SCHEDULED_TASK>).

  - Waits for the server's network address (config "bind") to exist, then starts the server with scripts/run_review_server.ps1.
  - Backs up the store only when the newest backup is older than 6 hours (every start would add about 1 GB), never deletes a backup.
  - Looks at the port every 30 seconds. When nobody listens, it starts the server again (at most 5 times per hour).
  - Writes <config logs>/autostart.log. Does not stop a running server.
  Usage: powershell -NoProfile -ExecutionPolicy Bypass -File scripts\start_review_server_at_logon.ps1 [-ConfigFile C:\path\server.json]
#>
param([string]$ConfigFile = (Join-Path $PSScriptRoot '..\..\..\work\report-config\server.json'))
$ErrorActionPreference = 'Continue'
$config = Get-Content -Raw -Encoding UTF8 -Path $ConfigFile | ConvertFrom-Json
New-Item -ItemType Directory -Force -Path $config.logs | Out-Null
$logFile = Join-Path $config.logs 'autostart.log'
function Log($message) { Add-Content -Path $logFile -Value ("{0:yyyy-MM-dd HH:mm:ss} {1}" -f (Get-Date), $message) -Encoding UTF8 }
function Listening { [bool](Get-NetTCPConnection -State Listen -LocalPort $config.port -ErrorAction SilentlyContinue) }
function WaitNetwork { for ($i = 0; $i -lt 90; $i++) { if (Get-NetIPAddress -IPAddress $config.bind -ErrorAction SilentlyContinue) { return $true }; Start-Sleep -Seconds 2 }; return $false }

Log 'watcher started'
if (-not (WaitNetwork)) { Log ('address {0} not found after 180 s, trying anyway' -f $config.bind) }
$restarts = @()
while ($true) {
    if (-not (Listening)) {
        $restarts = @($restarts | Where-Object { $_ -gt (Get-Date).AddHours(-1) })
        if ($restarts.Count -ge 5) { Log 'five starts in the last hour, waiting 5 minutes'; Start-Sleep -Seconds 300; continue }
        $newest = Get-ChildItem -Path $config.backups -Directory -ErrorAction SilentlyContinue | Sort-Object CreationTime -Descending | Select-Object -First 1
        $backup = (-not $newest) -or ($newest.CreationTime -lt (Get-Date).AddHours(-6))
        $arguments = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', (Join-Path $PSScriptRoot 'run_review_server.ps1'), '-ConfigFile', $ConfigFile)
        if (-not $backup) { $arguments += '-NoBackup' }
        Log ('server is not listening, starting it (backup: {0})' -f $backup)
        Start-Process -FilePath 'powershell.exe' -ArgumentList $arguments -WindowStyle Hidden | Out-Null
        $restarts += Get-Date
        for ($i = 0; $i -lt 90 -and -not (Listening); $i++) { Start-Sleep -Seconds 2 }
        Log ('listening after start: {0}' -f (Listening))
    }
    Start-Sleep -Seconds 30
}
