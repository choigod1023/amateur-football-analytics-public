param([Parameter(Mandatory=$true)][string]$BindIP)
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$python=Join-Path $root '.venv\Scripts\python.exe'
try {
    $env:DEMO_BIND_IP=$BindIP
    # Required by the shared configuration builder; both public options below
    # deliberately disable source filtering for this requested mode.
    $env:DEMO_SOURCE_IP='127.0.0.1'
    $env:DEMO_SRT_ALLOW_ANY='1'
    $env:DEMO_HTTP_ALLOW_ANY='1'
    Push-Location $root
    try { & $python -m app.demo_supervisor } finally { Pop-Location }
} finally {
    $env:DEMO_BIND_IP=$null
    $env:DEMO_SOURCE_IP=$null
    $env:DEMO_SRT_ALLOW_ANY=$null
    $env:DEMO_HTTP_ALLOW_ANY=$null
}
