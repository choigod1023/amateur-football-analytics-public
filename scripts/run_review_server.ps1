<#
  Start, stop or check the review and report server in one step (Windows PowerShell).

  Usage:
    .\scripts\run_review_server.ps1 -ConfigFile C:\path\to\server.json           start (stops an old instance, backs up the store first)
    .\scripts\run_review_server.ps1 -ConfigFile C:\path\to\server.json -Stop     stop
    .\scripts\run_review_server.ps1 -ConfigFile C:\path\to\server.json -Status   show whether it answers

  server.json (kept outside Git, it names a token file but never holds the token itself):
    {
      "store": "C:\\...\\public-own-match-review-20261111",
      "origin": "http://203.0.113.10:8443",
      "bind": "192.168.0.10",
      "port": 8443,
      "python": "C:\\...\\.venv\\Scripts\\python.exe",
      "token_file": "C:\\...\\upload-token.txt",
      "cameras": "C:\\...\\cameras.json",
      "detector": "C:\\...\\yolo11n.pt",
      "classifier": "C:\\...\\model.pt",
      "ffmpeg": "C:\\...\\ffmpeg.exe",
      "logs": "C:\\...\\review-server-logs",
      "backups": "C:\\...\\store-backups"
    }
#>
param(
    [Parameter(Mandatory = $true)][string]$ConfigFile,
    [switch]$Stop,
    [switch]$Status,
    [switch]$NoBackup
)
$ErrorActionPreference = 'Stop'
$config = Get-Content -Raw -Path $ConfigFile -Encoding UTF8 | ConvertFrom-Json
$project = Split-Path -Parent $PSScriptRoot

function Find-Server {
    Get-NetTCPConnection -State Listen -LocalPort $config.port -ErrorAction SilentlyContinue | Select-Object -First 1
}

if ($Status) {
    $listener = Find-Server
    if (-not $listener) { 'Not listening on port ' + $config.port; exit 1 }
    $headers = @{ Host = ([Uri]$config.origin).Authority }
    try {
        $answer = Invoke-RestMethod -Method Post -Uri ("http://{0}:{1}/api/v1/report/list" -f $config.bind, $config.port) -Headers ($headers + @{ Origin = $config.origin }) -ContentType 'application/json' -Body '{}'
        'Running (process {0}); worker alive: {1}; queued {2}, running {3}; free disk {4} GB; uploads enabled: {5}' -f $listener.OwningProcess, $answer.health.worker_alive, $answer.health.counts.queued, $answer.health.counts.running, $answer.health.disk_free_gb, $answer.upload_enabled
    } catch { 'Listening (process {0}) but the report API did not answer: {1}' -f $listener.OwningProcess, $_.Exception.Message; exit 2 }
    exit 0
}

$listener = Find-Server
if ($Stop -or $listener) {
    if ($listener) { Stop-Process -Id $listener.OwningProcess -Force; Start-Sleep -Seconds 2; 'Stopped process ' + $listener.OwningProcess }
    if ($Stop) { exit 0 }
}

if (-not $NoBackup) {
    $target = Join-Path $config.backups ('store-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
    New-Item -ItemType Directory -Force -Path $target | Out-Null
    robocopy $config.store $target /E /NFL /NDL /NJH /NJS /NP | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "Backup copy failed (robocopy exit code $LASTEXITCODE); the server was not started." }
    $global:LASTEXITCODE = 0     # robocopy 1 to 7 only say what was copied; do not hand that on as the exit code of this script
    $before = (Get-ChildItem $config.store -Recurse -File).Count
    $after = (Get-ChildItem $target -Recurse -File).Count
    if ($before -ne $after) { throw "Backup incomplete ($after of $before files); the server was not started." }
    "Backed up $after files to $target"
}

$env:FOOTBALL_REVIEW_ORIGIN = $config.origin
$env:FOOTBALL_REVIEW_DIR = $config.store
$env:FOOTBALL_REVIEW_BIND = $config.bind
$env:FOOTBALL_REVIEW_PORT = [string]$config.port
if ($config.live_snapshot_dir) { $env:FOOTBALL_LIVE_SNAPSHOT_DIR = $config.live_snapshot_dir }
$env:FOOTBALL_REPORT_TOKEN = (Get-Content -Raw -Path $config.token_file).Trim()
$env:FOOTBALL_REPORT_CAMERAS = $config.cameras
$env:FOOTBALL_REPORT_DETECTOR = $config.detector
$env:FOOTBALL_REPORT_CLASSIFIER = $config.classifier
$env:FOOTBALL_REPORT_FFMPEG = $config.ffmpeg
if ($config.ball_candidates -and $config.ball_reranker) { $env:FOOTBALL_REPORT_BALL_CANDIDATES = $config.ball_candidates; $env:FOOTBALL_REPORT_BALL_RERANKER = $config.ball_reranker }
$env:FOOTBALL_REPORT_CALIBRATIONS = Join-Path $config.store 'calibration\calibrations.json'
New-Item -ItemType Directory -Force -Path $config.logs | Out-Null
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
Start-Process -FilePath $config.python -ArgumentList '-m', 'app.review_public' -WorkingDirectory $project -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $config.logs "out-$stamp.log") -RedirectStandardError (Join-Path $config.logs "err-$stamp.log")
Start-Sleep -Seconds 7
$listener = Find-Server
if (-not $listener) { throw 'The server did not start. See the err log in ' + $config.logs }
'Started (process {0}) on {1}:{2}' -f $listener.OwningProcess, $config.bind, $config.port
