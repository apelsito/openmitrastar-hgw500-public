param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[0-9a-fA-F]{64}$')]
    [string]$OverlaySha256,

    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[0-9a-fA-F]{64}$')]
    [string]$ManifestSha256,

    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[0-9a-fA-F]{64}$')]
    [string]$Radio5StartSha256,

    [string]$OverlayPath = '',
    [string]$OverlayManifestPath = '',
    [string]$Radio5StartPath = '',
    [ValidateSet('autostart-secure', 'open-lab', 'open-lab-tqe512', 'open-lab-beacon-preflight', 'open-lab-beacon-lifetime')]
    [string]$Profile = 'autostart-secure',
    [ValidateSet(256, 512)]
    [int]$TqeRingEntries = 256,

    [ValidateRange(1, 32)]
    [int]$Jobs = 8,

    [switch]$ExpectAutostartEnabled,

    [switch]$PostValidateOnly,

    [switch]$Execute
)

$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$overlay = if ($OverlayPath) { [IO.Path]::GetFullPath($OverlayPath) } else { Join-Path $root 'work\mission-state\q3-dual-radio-autostart\build\openmitrastar-q3-dual-radio-autostart-overlay.tar.gz' }
$overlayManifest = if ($OverlayManifestPath) { [IO.Path]::GetFullPath($OverlayManifestPath) } else { Join-Path $root 'work\mission-state\q3-dual-radio-autostart\build\manifest.json' }
$radio5Start = if ($Radio5StartPath) { [IO.Path]::GetFullPath($Radio5StartPath) } else { Join-Path $root 'work\mission-state\q3-dual-radio-autostart\rootfs\usr\sbin\om-radio5-start' }
$buildScript = Join-Path $root 'tools\build_q3_persistent_composite.sh'
$testScript = Join-Path $root 'tools\test_q3_persistent_composite.py'
$buildDir = Join-Path $root 'work\mission-state\q3-persistent-composite\build'
$candidate = Join-Path $buildDir 'openmitrastar-linux510-q3-persistent-v1-LZMA-OFFLINE-NO-FLASH.webformat.bin'
$candidateA = Join-Path $buildDir 'openmitrastar-linux510-q3-persistent-v1-LZMA-OFFLINE-NO-FLASH-a.webformat.bin'
$candidateB = Join-Path $buildDir 'openmitrastar-linux510-q3-persistent-v1-LZMA-OFFLINE-NO-FLASH-b.webformat.bin'
$candidateManifest = Join-Path $buildDir 'manifest.json'
$checksums = Join-Path $buildDir 'SHA256SUMS'
$tftp = Join-Path $root 'work\tftp\omvl\linux510-q3-persistent-v1-LZMA-RAM-TEST-NO-FLASH.bin'
$resultPath = Join-Path $root 'work\mission-state\q3-persistent-composite\recompose-last.json'
$slotBytes = 0x7a0000

$supersededOverlayHashes = @(
    '3c60bdd08d972950252fa0799b5c750124f6450b1c98958a1ad993c3c9b29f7a',
    '7f4f458eea5c361da8769703a6e58eb6d0b356706d8fd743308cd1604068f9a4',
    'b1acd635780f6a4c915c70a1c7023ff119b346292f5cc6bd773616c3fa29102f',
    '62dea0d9b44b12023729c987f9127b3cd55c8b1a8123f5d53dd8ccb8ff5128fe',
    '4dce26ecea65094a5aa5360ab25624726b9ee7b408a88ea875514572f43edc14',
    '2b7b96f3850edc8cc132e5a906d5da7b0a3fbe87b1a53fc987ca5d0530021e65',
    'dd879b5bdbb5db842033e9578be3f2a4470d0ab765c4a15c99aeaa6c0d286937',
    '5ea89f9883ba0d76c9e08c697474eb8a7913fe1878a206636180b948e3cfb7bd',
    'beb282c8fdb4d5f3104c278f42e62a8311a55e3f3ddcfbb1ad53412bbb64906e',
    '5a52e4694a2490d903504aab3698e91d965bc77c31e3c74045760cfb1f11bdfe',
    'ce111febb1bc70aac6637568e858b4bc998fbffa7e529a09b5c06ae2a6fd3e7d',
    'f83617246d5e65330d6263ebf695382afe1977d9310406fc2763621331df0671',
    '9700772003e6f0245c62de8307644896f4367ffa5af909614b5f7bd4834e646d',
    '14a97a125ea13b7a1467d9122987ebd4431c9b280469403a0c04f5dd23eef410',
    '4c5f25467c0b68d861347367aa43db0538a05080ad7b4d14165bd92f9a8ee64f',
    'ee65fcf8981f253981b36b51f887a3a32480d3b2e51f924b894d93c7afde634b'
)

function Get-Sha256([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Missing required input: $Path"
    }
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Convert-ToWslPath([string]$Path) {
    $full = [IO.Path]::GetFullPath($Path)
    if ($full -notmatch '^([A-Za-z]):\\(.*)$') { throw "Cannot map path to WSL: $full" }
    return "/mnt/$($matches[1].ToLowerInvariant())/$($matches[2].Replace('\','/'))"
}

$expectedOverlay = $OverlaySha256.ToLowerInvariant()
$expectedManifest = $ManifestSha256.ToLowerInvariant()
$expectedStart = $Radio5StartSha256.ToLowerInvariant()
$actualOverlay = Get-Sha256 $overlay
$actualManifest = Get-Sha256 $overlayManifest
$actualStart = Get-Sha256 $radio5Start

if ($actualOverlay -ne $expectedOverlay) {
    throw "Overlay hash mismatch expected=$expectedOverlay actual=$actualOverlay"
}
if ($actualManifest -ne $expectedManifest) {
    throw "Overlay manifest hash mismatch expected=$expectedManifest actual=$actualManifest"
}
if ($actualStart -ne $expectedStart) {
    throw "om-radio5-start hash mismatch expected=$expectedStart actual=$actualStart"
}

$manifest = Get-Content -LiteralPath $overlayManifest -Raw | ConvertFrom-Json
if ($manifest.archive.sha256 -ne $expectedOverlay) {
    throw 'Overlay manifest does not bind the supplied archive hash'
}
$expectedAutostart = [bool]$ExpectAutostartEnabled
if ([bool]$manifest.autostart_enabled_by_default -ne $expectedAutostart -or
    $manifest.hardware_actions -ne $false -or $manifest.flash_actions -ne $false) {
    throw 'Overlay safety contract drifted'
}
if ($manifest.reproducibility.identical -ne $true -or
    $manifest.reproducibility.a.sha256 -ne $expectedOverlay -or
    $manifest.reproducibility.b.sha256 -ne $expectedOverlay) {
    throw 'Overlay A/B reproducibility contract failed'
}
if ($Profile -like 'open-lab*') {
    $expectedClassification = if ($Profile -eq 'open-lab-tqe512') { 'OPEN-LAB-TQE512-DISCRIMINATOR-RAM-ONLY-NO-FLASH' } elseif ($Profile -eq 'open-lab-beacon-preflight') { 'OPEN-LAB-BEACON-PREFLIGHT-RAM-ONLY-NO-FLASH' } elseif ($Profile -eq 'open-lab-beacon-lifetime') { 'OPEN-LAB-BEACON-LIFETIME-RAM-ONLY-NO-FLASH' } else { 'OPEN-LAB-RAM-ONLY-NO-FLASH' }
    if ($manifest.classification -ne $expectedClassification -or
        $manifest.profile -ne $Profile -or $manifest.psk_required -ne $false -or
        $manifest.psk_bundled -ne $false) {
        throw 'OPEN-LAB overlay contract drifted'
    }
}
if ([int]$manifest.contract.radio5g.switch_tqe_rx_ring_entries -ne $TqeRingEntries) {
    throw "TQE ring contract mismatch expected=$TqeRingEntries actual=$($manifest.contract.radio5g.switch_tqe_rx_ring_entries)"
}

$isSuperseded = $supersededOverlayHashes -contains $expectedOverlay
$preflight = [ordered]@{
    schema = 'openmitrastar.q3-overlay-recompose-preflight/v1'
    overlay_sha256 = $expectedOverlay
    manifest_sha256 = $expectedManifest
    radio5_start_sha256 = $expectedStart
    profile = $Profile
    tqe_ring_entries = $TqeRingEntries
    overlay_ab_reproducible = $true
    autostart_default = [bool]$manifest.autostart_enabled_by_default
    slot_bytes = $slotBytes
    tftp_destination = $tftp
    build_command = 'wsl.exe -e sh -lc "cd /workspace/user-home/Desktop/MitraStar && OM_Q3_EXPECTED_* TOPAZ_JOBS=N sh tools/build_q3_persistent_composite.sh"'
    execute_requested = [bool]$Execute
    superseded_overlay = $isSuperseded
    flash_actions = $false
    hardware_actions = $false
}
$preflight | ConvertTo-Json -Depth 6

if (-not $Execute) {
    if ($isSuperseded) {
        Write-Host 'OMQ3_RECOMPOSE_WAIT_NEW_OVERLAY current_overlay_is_superseded=1 execute=0'
    } else {
        Write-Host 'OMQ3_RECOMPOSE_PREFLIGHT_PASS execute=0'
    }
    exit 0
}
if ($isSuperseded) {
    throw 'Refusing to compose a known superseded overlay'
}

$workspaceWsl = '/workspace/user-home/Desktop/MitraStar'
$overlayWsl = Convert-ToWslPath $overlay
$manifestWsl = Convert-ToWslPath $overlayManifest
$startWsl = Convert-ToWslPath $radio5Start
$buildCommand = @"
set -eu
cd '$workspaceWsl'
export OM_Q3_EXPECTED_RADIO5_OVERLAY_SHA256='$expectedOverlay'
export OM_Q3_EXPECTED_RADIO5_MANIFEST_SHA256='$expectedManifest'
export OM_Q3_EXPECTED_RADIO5_START_SHA256='$expectedStart'
export OM_Q3_RADIO5_OVERLAY_PATH='$overlayWsl'
export OM_Q3_RADIO5_MANIFEST_PATH='$manifestWsl'
export OM_Q3_RADIO5_START_PATH='$startWsl'
export OM_Q3_PROFILE='$Profile'
export OM_Q3_TQE_RING_ENTRIES='$TqeRingEntries'
export TOPAZ_JOBS='$Jobs'
sh tools/build_q3_persistent_composite.sh
"@
if (-not $PostValidateOnly) {
    & wsl.exe -e sh -lc $buildCommand
    if ($LASTEXITCODE -ne 0) { throw "Q3 compositor failed rc=$LASTEXITCODE" }
}

$postCommand = @"
set -eu
cd '$workspaceWsl'
export OM_Q3_EXPECTED_RADIO5_START_SHA256='$expectedStart'
export OM_Q3_PROFILE='$Profile'
export OM_Q3_TQE_RING_ENTRIES='$TqeRingEntries'
python3 tools/test_q3_persistent_composite.py
sha256sum -c work/mission-state/q3-persistent-composite/build/SHA256SUMS
cmp -s work/mission-state/q3-persistent-composite/build/openmitrastar-linux510-q3-persistent-v1-LZMA-OFFLINE-NO-FLASH-a.webformat.bin work/mission-state/q3-persistent-composite/build/openmitrastar-linux510-q3-persistent-v1-LZMA-OFFLINE-NO-FLASH-b.webformat.bin
cmp -s work/mission-state/q3-persistent-composite/build/openmitrastar-linux510-q3-persistent-v1-LZMA-OFFLINE-NO-FLASH.webformat.bin work/tftp/omvl/linux510-q3-persistent-v1-LZMA-RAM-TEST-NO-FLASH.bin
"@
& wsl.exe -e sh -lc $postCommand
if ($LASTEXITCODE -ne 0) { throw "Q3 post-build validation failed rc=$LASTEXITCODE" }

$candidateHash = Get-Sha256 $candidate
$tftpHash = Get-Sha256 $tftp
$candidateBytes = (Get-Item -LiteralPath $candidate).Length
if ($candidateBytes -le 0 -or $candidateBytes -gt $slotBytes) {
    throw "Q3 candidate outside linux_live slot: $candidateBytes"
}
if ($candidateHash -ne $tftpHash) { throw 'TFTP copy differs from Q3 candidate' }
if ((Get-Sha256 $candidateA) -ne (Get-Sha256 $candidateB)) {
    throw 'Q3 A/B webformat mismatch'
}
$builtManifest = Get-Content -LiteralPath $candidateManifest -Raw | ConvertFrom-Json
if ($builtManifest.slot.fits -ne $true -or $builtManifest.slot.bootbase_contract -ne 'PASS') {
    throw 'Q3 manifest slot/Bootbase gate failed'
}

$result = [ordered]@{
    schema = 'openmitrastar.q3-overlay-recompose-result/v1'
    created_utc = [DateTime]::UtcNow.ToString('o')
    candidate = $candidate
    candidate_sha256 = $candidateHash
    candidate_bytes = $candidateBytes
    slot_bytes = $slotBytes
    spare_bytes = $slotBytes - $candidateBytes
    tftp = $tftp
    tftp_sha256 = $tftpHash
    overlay_sha256 = $expectedOverlay
    overlay_manifest_sha256 = $expectedManifest
    radio5_start_sha256 = $expectedStart
    profile = $Profile
    tqe_ring_entries = $TqeRingEntries
    ab_reproducible = $true
    bootbase_contract = 'PASS'
    tests = 'PASS'
    flash_actions = $false
    hardware_actions = $false
}
$result | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $resultPath -Encoding utf8NoBOM
$result | ConvertTo-Json -Depth 6
Write-Host "OMQ3_RECOMPOSE_PASS sha256=$candidateHash bytes=$candidateBytes spare=$($slotBytes - $candidateBytes) flash=0 hardware=0"
