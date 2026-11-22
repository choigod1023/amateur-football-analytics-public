<#
  Record the incoming Moblin stream (read from MediaMTX over RTSP) to disk in 10-minute pieces, without re-encoding.
  It waits until the stream exists and starts again whenever the stream stops (a break in the sender, halftime).
  Usage: .\scripts\record_stream_loop.ps1 [-OutDir <folder>]
  Stop: close the window or press Ctrl+C. Pieces are named <date>_<time>.mp4 (fragmented MP4, so a cut file is still playable).
#>
param(
    [string]$OutDir = (Join-Path $PSScriptRoot '..\..\football-coach-server\recordings\match-1118'),
    [string]$Ffmpeg = (Join-Path $PSScriptRoot '..\..\..\work\ffmpeg-local\ffmpeg-9.0.2-essentials_build\bin\ffmpeg.exe'),
    [string]$Url = 'rtsp://127.0.0.1:18554/match'
)
New-Item -ItemType Directory -Force $OutDir | Out-Null
$log = Join-Path $OutDir 'record.log'
while ($true) {
    "$(Get-Date -Format 'HH:mm:ss') start recording attempt" | Add-Content $log
    & $Ffmpeg -hide_banner -loglevel warning -rtsp_transport tcp -i $Url -c copy -f segment -segment_time 600 -reset_timestamps 1 `
        -segment_format mp4 -segment_format_options movflags=frag_keyframe+empty_moov -strftime 1 (Join-Path $OutDir '%Y-%m-%d_%H-%M-%S.mp4') 2>> $log
    "$(Get-Date -Format 'HH:mm:ss') ffmpeg ended (code $LASTEXITCODE), retry in 5 s" | Add-Content $log
    Start-Sleep 5
}
