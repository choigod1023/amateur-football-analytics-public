param([ValidateSet('Check','Apply','Remove','CheckCellular','AllowCellular','CheckViewers','AllowViewers')][string]$Action='Check', [string]$PeerFile)
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$python=Join-Path $root '.venv\Scripts\python.exe'
$media=Join-Path $root 'mediamtx\mediamtx.exe'
$names=@('FootballCoach-Demo-SRT-8890','FootballCoach-Demo-HTTP-8443')
$isAdmin=([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if(-not (Test-Path -LiteralPath $python -PathType Leaf) -or -not (Test-Path -LiteralPath $media -PathType Leaf)) { throw 'Project Python or MediaMTX is unavailable.' }
$peer=if($PeerFile) { [System.IO.File]::ReadAllText((Resolve-Path -LiteralPath $PeerFile).Path).Trim() } else { $env:FOOTBALL_DEMO_PEER }
$env:FOOTBALL_DEMO_PEER=$peer
try {
    $peerAddress=[System.Net.IPAddress]::Parse($peer)
    if($peerAddress.AddressFamily -ne [System.Net.Sockets.AddressFamily]::InterNetwork -or $peer -eq '0.0.0.0' -or $peerAddress.IsIPv6Multicast -or [System.Net.IPAddress]::IsLoopback($peerAddress)) { throw 'Invalid peer.' }
    & $python (Join-Path $PSScriptRoot 'validate_demo_peer.py')
    if($LASTEXITCODE -ne 0) { throw 'A single global sender IPv4 is required.' }
    $basePython=& $python -c 'import sys; print(sys._base_executable)'
    if($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $basePython -PathType Leaf)) { throw 'Python executable could not be verified.' }
    if($Action -in @('CheckCellular','AllowCellular')) {
        $srt=Get-NetFirewallRule -Name $names[0] -ErrorAction Stop
        $p=$srt|Get-NetFirewallPortFilter; $a=$srt|Get-NetFirewallAddressFilter; $f=$srt|Get-NetFirewallApplicationFilter
        $allowed=@($peer,($peer+'/32'),($peer+'/255.255.255.255'),'Any')
        if($srt.Enabled -ne 'True' -or $srt.Direction -ne 'Inbound' -or $srt.Action -ne 'Allow' -or $p.Protocol -ne 'UDP' -or $p.LocalPort -ne '8890' -or $f.Program -ne $media -or @($a.RemoteAddress).Count -ne 1 -or $allowed -notcontains [string]@($a.RemoteAddress)[0]) { throw 'Existing SRT rule does not match the expected scope.' }
        if($Action -eq 'CheckCellular') { Write-Output 'SRT rule is eligible for cellular source update; no changes made.'; return }
        if(-not $isAdmin) { throw 'Administrator permission is required for the SRT source update.' }
        Set-NetFirewallRule -Name $names[0] -RemoteAddress Any
        $updated=Get-NetFirewallRule -Name $names[0] | Get-NetFirewallAddressFilter
        if(@($updated.RemoteAddress).Count -ne 1 -or [string]@($updated.RemoteAddress)[0] -ne 'Any') { throw 'SRT source update could not be verified.' }
        Write-Output 'SRT rule updated for cellular sources; HTTP rule was not changed.'
        return
    }
    if($Action -in @('CheckViewers','AllowViewers')) {
        $http=Get-NetFirewallRule -Name $names[1] -ErrorAction Stop
        $p=$http|Get-NetFirewallPortFilter; $a=$http|Get-NetFirewallAddressFilter; $f=$http|Get-NetFirewallApplicationFilter
        $allowed=@($peer,($peer+'/32'),($peer+'/255.255.255.255'),'Any')
        if($http.Enabled -ne 'True' -or $http.Direction -ne 'Inbound' -or $http.Action -ne 'Allow' -or $p.Protocol -ne 'TCP' -or $p.LocalPort -ne '8443' -or $f.Program -ne $basePython -or @($a.RemoteAddress).Count -ne 1 -or $allowed -notcontains [string]@($a.RemoteAddress)[0]) { throw 'Existing HTTP rule does not match the expected scope.' }
        if($Action -eq 'CheckViewers') { Write-Output 'HTTP rule is eligible for source update; no changes made.'; return }
        if(-not $isAdmin) { throw 'Administrator permission is required for the HTTP source update.' }
        Set-NetFirewallRule -Name $names[1] -RemoteAddress Any
        $updated=Get-NetFirewallRule -Name $names[1] | Get-NetFirewallAddressFilter
        if(@($updated.RemoteAddress).Count -ne 1 -or [string]@($updated.RemoteAddress)[0] -ne 'Any') { throw 'HTTP source update could not be verified.' }
        Write-Output 'HTTP rule updated for all sources; SRT rule was not changed.'
        return
    }
    if($Action -eq 'Remove') {
        if(-not $isAdmin) { throw 'Administrator permission is required to remove the two temporary rules.' }
        foreach($i in 0..1) {
            $r=Get-NetFirewallRule -Name $names[$i] -ErrorAction SilentlyContinue
            if(-not $r) { continue }
            $p=$r|Get-NetFirewallPortFilter; $a=$r|Get-NetFirewallAddressFilter; $f=$r|Get-NetFirewallApplicationFilter
            $allowed=@($peer,($peer+'/32'),($peer+'/255.255.255.255'))
            $allowed+= 'Any'
            if($r.Direction -ne 'Inbound' -or $r.Action -ne 'Allow' -or $p.Protocol -ne @('UDP','TCP')[$i] -or $p.LocalPort -ne @('8890','8443')[$i] -or $f.Program -ne @($media,$basePython)[$i] -or @($a.RemoteAddress).Count -ne 1 -or $allowed -notcontains [string]@($a.RemoteAddress)[0]) { throw 'Existing rule does not match the expected temporary scope; it was not removed.' }
            Remove-NetFirewallRule -Name $names[$i]
        }
        Write-Output 'Matching temporary demo rules removed or already absent.'
        return
    }
    foreach($name in $names) { if(Get-NetFirewallRule -Name $name -ErrorAction SilentlyContinue) { throw 'A demo rule name is already in use; inspect before proceeding.' } }
    if($Action -eq 'Check') {
        Write-Output 'Source format, executables and rule names checked. No firewall changes made.'
        Write-Output ('Administrator token available: ' + $isAdmin)
        Write-Output ('HTTP executable: ' + $basePython)
        return
    }
    if(-not $isAdmin) { throw 'Administrator permission is required to add the temporary rules.' }
    $created=@()
    try {
        New-NetFirewallRule -Name $names[0] -DisplayName 'Football demo SRT 8890' -Direction Inbound -Action Allow -Enabled True -Profile Any -Protocol UDP -LocalPort 8890 -Program $media -RemoteAddress ($peer+'/32') | Out-Null
        $created += $names[0]
        New-NetFirewallRule -Name $names[1] -DisplayName 'Football demo HTTP 8443' -Direction Inbound -Action Allow -Enabled True -Profile Any -Protocol TCP -LocalPort 8443 -Program $basePython -RemoteAddress ($peer+'/32') | Out-Null
        $created += $names[1]
        foreach($i in 0..1) {
            $r=Get-NetFirewallRule -Name $names[$i]; $p=$r|Get-NetFirewallPortFilter; $a=$r|Get-NetFirewallAddressFilter; $f=$r|Get-NetFirewallApplicationFilter
            $expectedProtocol=@('UDP','TCP')[$i]; $expectedPort=@('8890','8443')[$i]; $expectedProgram=@($media,$basePython)[$i]
            $allowed=@($peer,($peer+'/32'),($peer+'/255.255.255.255'))
            if($r.Enabled -ne 'True' -or $r.Direction -ne 'Inbound' -or $r.Action -ne 'Allow' -or $p.Protocol -ne $expectedProtocol -or $p.LocalPort -ne $expectedPort -or $f.Program -ne $expectedProgram -or @($a.RemoteAddress).Count -ne 1 -or $allowed -notcontains [string]@($a.RemoteAddress)[0]) { throw 'Rule verification failed.' }
        }
        Write-Output 'Two source-restricted temporary demo rules created and verified.'
    } catch {
        foreach($name in $created) { Remove-NetFirewallRule -Name $name -ErrorAction SilentlyContinue }
        throw 'Could not safely create or verify the demo rules; newly created rules were removed where possible.'
    }
} finally { $peer=$null; $peerAddress=$null }
