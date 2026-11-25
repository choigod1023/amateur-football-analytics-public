<#
  Match day start: the SRT receiver (MediaMTX through app.plaintext_demo srt) and the recorder loop, each only when it is not running yet,
  then a check of the review server (started at logon by the task FootballReviewServer) and the addresses to open.
  It only starts the existing programs the same way as on 2026-11-18; it changes no streaming or recording setting.
  Usage: powershell -NoProfile -ExecutionPolicy Bypass -File scripts\start_match_day.ps1 [-MatchName match-20261120] [-DryRun]
#>
param(
    [string]$MatchName = ('match-' + (Get-Date -Format 'yyyyMMdd')),
    [switch]$DryRun
)
$base = $env:FOOTBALL_OUTPUTS_DIR   # the folder that holds football-coach-server
if (-not $base) { throw 'Set FOOTBALL_OUTPUTS_DIR to the folder that holds football-coach-server.' }
$server = Join-Path $base 'football-coach-server'
$python = Join-Path $server '.venv\Scripts\python.exe'
$recordScript = Join-Path $PSScriptRoot 'record_stream_loop.ps1'
$outDir = Join-Path $server ('recordings\' + $MatchName)
function Listening($port) { [bool](Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue) }
function Say($m) { Write-Host ("{0:HH:mm:ss} {1}" -f (Get-Date), $m) }

# 1. SRT receiver
if (Get-Process -Name mediamtx -ErrorAction SilentlyContinue) { Say 'SRT receiver (MediaMTX) already running' }
elseif ($DryRun) { Say "would start: $python -m app.plaintext_demo srt (in $server)" }
else {
    Start-Process -FilePath $python -ArgumentList '-m', 'app.plaintext_demo', 'srt' -WorkingDirectory $server -WindowStyle Minimized | Out-Null
    for ($i = 0; $i -lt 30 -and -not (Listening 18554); $i++) { Start-Sleep -Seconds 2 }
    Say ('SRT receiver started, RTSP port 18554 listening: {0}' -f (Listening 18554))
}

# 2. Recorder (waits by itself until Moblin sends)
$recording = Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" | Where-Object { $_.CommandLine -match 'record_stream_loop' }
if ($recording) { Say 'recorder loop already running' }
elseif ($DryRun) { Say "would start the recorder into $outDir" }
else {
    Start-Process -FilePath 'powershell.exe' -ArgumentList '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $recordScript, '-OutDir', $outDir -WindowStyle Minimized | Out-Null
    Say "recorder started, pieces go to $outDir"
}

# 3. Review server
Say ('review server on 8443 listening: {0}' -f (Listening 8443))
Say 'Moblin: send to srt://<public address>:8890 as on 2026-11-18'
Say 'Phone: http://<server address>:8443/tag (analyst buttons), /bench (coach screen), /live (video)'
Say 'After the match: python scripts\cut_halves_from_tags.py --store <review store> --day <date> --out-dir <folder> --small'
