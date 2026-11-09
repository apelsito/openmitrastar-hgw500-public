[CmdletBinding()]
param(
    [string]$HostAddress = '192.168.1.90',
    [string]$Bundle = '',
    [string]$RemoteRoot = '/tmp/openmitrastar-all64-autorate',
    [int]$WaitForQ2Seconds = 180,
    [switch]$ExecuteHotload,
    [switch]$ExecuteRollback,
    [string]$AckRamOnly = ''
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
if (-not $Bundle) {
    $Bundle = Join-Path $root 'outputs\kernel-port\realtek-loop\all64-autorate-q2-hotload-RAM-ONLY-NO-FLASH'
}
$bundlePath = (Resolve-Path $Bundle).Path
$execTool = Join-Path $root 'tools\ramssh_exec.py'
$uploadTool = Join-Path $root 'tools\ramssh_upload.py'
$expectedKernel = '5.10.260-openmitrastar-radiohw'
$applyAck = 'OPENMITRASTAR_ALL64_AUTORATE_RAM_ONLY'
$rollbackAck = 'OPENMITRASTAR_ALL64_AUTORATE_ROLLBACK_RAM_ONLY'

if ($ExecuteHotload -and $ExecuteRollback) {
    throw 'Choose only one of -ExecuteHotload or -ExecuteRollback.'
}

$required = @(
    'ram_insmod',
    'MODULE_SHA256SUMS',
    'modules\rtlwifi.ko',
    'modules\btcoexist.ko',
    'modules\rtl_pci.ko',
    'modules\rtl8192ee.ko',
    'scripts\apply-all64-autorate.sh',
    'scripts\rollback-all64-autorate.sh'
)
foreach ($relative in $required) {
    if (-not (Test-Path -LiteralPath (Join-Path $bundlePath $relative))) {
        throw "Missing bundle artifact: $relative"
    }
}

$expectedHashes = @{
    'ram_insmod' = '8eb902dcc5e1bdab1aba356aafca04102ab394352c1685434ac9a9a09c5baba6'
    'modules\rtlwifi.ko' = '9b7988816abb5065cd5a2a39defba608d073646aac15c75e244ac5cd95e096ee'
    'modules\btcoexist.ko' = 'c299e80b7b210c8b394815f56b68a1c1eba9e54ea5e807a4738f9b4bec19573f'
    'modules\rtl_pci.ko' = '9a0c66835b9c135deb90382e0e325165b76a79982544e6c2ceacb663540c1ea8'
    'modules\rtl8192ee.ko' = '7d59c11311011f7b43bc6e47b0d8652cc60b653f7b22ea58d85246d0c32ebf70'
}
foreach ($entry in $expectedHashes.GetEnumerator()) {
    $actual = (Get-FileHash -LiteralPath (Join-Path $bundlePath $entry.Key) -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $entry.Value) { throw "Hash mismatch: $($entry.Key)" }
}

$plan = [ordered]@{
    schema = 'openmitrastar.all64-autorate-hotload-plan/v1'
    host = $HostAddress
    expected_kernel = $expectedKernel
    bundle = $bundlePath
    remote_root = $RemoteRoot
    profile = 'all64 automatic-rate Q2 post-boot'
    matching_modules = @('ctr.ko', 'ccm.ko', 'cmac.ko', 'cfg80211.ko', 'libarc4.ko', 'mac80211.ko', 'rtlwifi.ko', 'btcoexist.ko', 'rtl_pci.ko', 'rtl8192ee.ko')
    rtl_pci_hgw_parameters = 'all default/off'
    rtl8192ee = [ordered]@{
        force_txbd64_width = $true
        tx_dma_wmb = $true
        tx_close_diag = $true
        tx_page_units = 2
        tx_pbp_256 = $false
        disable_watchdog = $false
        automatic_rate = $true
        forced_rates = $false
        data_split = $false
        rate_trace = $false
    }
    rollback = 'installed Q2 radio module set'
    mutations = $false
    flash = $false
}

if (-not $ExecuteHotload -and -not $ExecuteRollback) {
    $plan | ConvertTo-Json -Depth 6
    Write-Output 'OMALL64_PLAN_ONLY_PASS=1'
    exit 0
}

$requiredAck = if ($ExecuteRollback) { $rollbackAck } else { $applyAck }
if ($AckRamOnly -ne $requiredAck) { throw "Exact -AckRamOnly $requiredAck required." }

$deadline = (Get-Date).AddSeconds($WaitForQ2Seconds)
$ready = $false
$probeCommand = 'uname -r; cat /sys/class/net/eth0/carrier; echo OM_Q2_READY=1'
do {
    $probe = & python $execTool --host $HostAddress --timeout 8 $probeCommand 2>&1
    $probeText = $probe -join "`n"
    if ($LASTEXITCODE -eq 0 -and
        $probeText -match [regex]::Escape($expectedKernel) -and
        $probeText -match '(?m)^1\r?$' -and
        $probeText -match 'OM_Q2_READY=1') {
        $ready = $true
        break
    }
    Start-Sleep -Seconds 2
} while ((Get-Date) -lt $deadline)
if (-not $ready) { throw "Q2 SSH/kernel/eth0 carrier gate did not become ready at $HostAddress." }

& python $execTool --host $HostAddress --timeout 15 "rm -rf '$RemoteRoot'; mkdir -p '$RemoteRoot/modules' '$RemoteRoot/scripts'" | Out-Host
if ($LASTEXITCODE -ne 0) { throw 'Could not prepare remote RAM directory.' }

function Send-Artifact([string]$relative, [string]$mode) {
    $source = Join-Path $bundlePath $relative
    $remote = "$RemoteRoot/" + ($relative -replace '\\','/')
    & python $uploadTool $source $remote --host $HostAddress --mode $mode | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "Upload failed: $relative" }
}

Send-Artifact 'ram_insmod' '0700'
Send-Artifact 'MODULE_SHA256SUMS' '0600'
Send-Artifact 'scripts\apply-all64-autorate.sh' '0700'
Send-Artifact 'scripts\rollback-all64-autorate.sh' '0700'
if ($ExecuteHotload) {
    Send-Artifact 'modules\ctr.ko' '0600'
    Send-Artifact 'modules\ccm.ko' '0600'
    Send-Artifact 'modules\cmac.ko' '0600'
    Send-Artifact 'modules\cfg80211.ko' '0600'
    Send-Artifact 'modules\libarc4.ko' '0600'
    Send-Artifact 'modules\mac80211.ko' '0600'
    Send-Artifact 'modules\rtlwifi.ko' '0600'
    Send-Artifact 'modules\btcoexist.ko' '0600'
    Send-Artifact 'modules\rtl_pci.ko' '0600'
    Send-Artifact 'modules\rtl8192ee.ko' '0600'
}

$remoteScript = if ($ExecuteRollback) { 'rollback-all64-autorate.sh' } else { 'apply-all64-autorate.sh' }
$command = "'$RemoteRoot/scripts/$remoteScript' '$requiredAck' '$RemoteRoot'"
$result = & python $execTool --host $HostAddress --timeout 120 $command 2>&1
$result | Out-Host
if ($LASTEXITCODE -ne 0) { throw "$remoteScript failed." }

if ($ExecuteHotload -and ($result -join "`n") -notmatch 'OMALL64_HOTLOAD_PASS=1') {
    throw 'Hotload did not return the final PASS marker.'
}
if ($ExecuteRollback -and ($result -join "`n") -notmatch 'OMALL64_ROLLBACK_PASS=1') {
    throw 'Rollback did not return the final PASS marker.'
}
