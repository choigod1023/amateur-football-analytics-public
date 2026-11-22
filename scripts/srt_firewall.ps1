param(
    [ValidateSet('Check', 'Apply', 'Remove')]
    [string]$Action = 'Check',
    [string]$PrivateKeyPath,
    [string]$CiphertextPath
)
$ErrorActionPreference = 'Stop'
$ruleName = 'FootballCoach-SRT-Temporary-8890'
$root = Split-Path -Parent $PSScriptRoot
$program = Join-Path $root 'mediamtx\mediamtx.exe'
$python = Join-Path $root '.venv\Scripts\python.exe'
$decoder = Join-Path $PSScriptRoot 'decrypt_source_ip.py'
$principal = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
$isAdmin = $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if ($Action -eq 'Remove') {
    if (-not $isAdmin) { throw 'Removing the temporary rule requires an elevated administrator session.' }
    $rule = Get-NetFirewallRule -Name $ruleName -ErrorAction SilentlyContinue
    if ($rule) { Remove-NetFirewallRule -Name $ruleName }
    Write-Output 'Temporary rule removed or already absent.'
    return
}
if (-not (Test-Path -LiteralPath $program -PathType Leaf)) { throw 'MediaMTX executable is missing.' }
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw 'Project Python is missing.' }
if (-not $PrivateKeyPath -or -not $CiphertextPath) { throw 'Provide the private-key and ciphertext file paths.' }
$source = & $python $decoder $PrivateKeyPath $CiphertextPath
if ($LASTEXITCODE -ne 0 -or -not $source) { throw 'Sender validation failed.' }
try {
    $parsed = [System.Net.IPAddress]::Parse($source)
    if ($parsed.AddressFamily -ne [System.Net.Sockets.AddressFamily]::InterNetwork) { throw 'Not IPv4.' }
    $existing = Get-NetFirewallRule -Name $ruleName -ErrorAction SilentlyContinue
    if ($existing) { throw 'The temporary rule name already exists; inspect it before proceeding.' }
    if ($Action -eq 'Check') {
        Write-Output 'Executable and encrypted sender validated; temporary rule name is unused. No changes made.'
        Write-Output ('Administrator token available: ' + $isAdmin)
        return
    }
    if (-not $isAdmin) { throw 'Applying the temporary rule requires an elevated administrator session.' }
    New-NetFirewallRule -Name $ruleName -DisplayName 'Football Coach temporary SRT test' -Direction Inbound -Action Allow -Enabled True -Profile Any -Protocol UDP -LocalPort 8890 -Program $program -RemoteAddress ($source + '/32') | Out-Null
    $created = Get-NetFirewallRule -Name $ruleName
    $p = $created | Get-NetFirewallPortFilter
    $a = $created | Get-NetFirewallAddressFilter
    $app = $created | Get-NetFirewallApplicationFilter
    $allowedForms = @($source, ($source + '/32'), ($source + '/255.255.255.255'))
    if ($created.Direction -ne 'Inbound' -or $created.Action -ne 'Allow' -or $p.Protocol -ne 'UDP' -or $p.LocalPort -ne '8890' -or $app.Program -ne $program -or @($a.RemoteAddress).Count -ne 1 -or $allowedForms -notcontains [string]@($a.RemoteAddress)[0]) {
        Remove-NetFirewallRule -Name $ruleName
        throw 'Rule verification failed; the newly created rule was removed.'
    }
    Write-Output 'Temporary source-restricted SRT rule created and verified.'
} finally {
    $source = $null
    $parsed = $null
}
