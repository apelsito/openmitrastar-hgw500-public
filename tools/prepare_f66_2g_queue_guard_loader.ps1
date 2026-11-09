[CmdletBinding(PositionalBinding = $false)]
param(
    [string]$SourceLoader = "/workspace/user-home\Desktop\MitraStar\work\mission-state\w4-rootfs-product\rootfs\usr\sbin\om-radio-modules",
    [string]$OutputDir = "/workspace/user-home\Desktop\MitraStar\work\mission-state\q3-persistent-composite-f66-2g-queue-guard\prep"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$OutputDir = [IO.Path]::GetFullPath($OutputDir)
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$out = Join-Path $OutputDir "om-radio-modules"
$result = Join-Path $OutputDir "f66-loader-prep.json"

if (-not (Test-Path -LiteralPath $SourceLoader -PathType Leaf)) {
    throw "missing source loader: $SourceLoader"
}

$text = Get-Content -LiteralPath $SourceLoader -Raw
$originalSha = (Get-FileHash -Algorithm SHA256 -LiteralPath $SourceLoader).Hash.ToLowerInvariant()

$oldParams = 'parameters="hgw500_eapol_trace=$radio2g_eapol_trace hgw500_eapol_mgnt_queue=$radio2g_eapol_mgnt_queue"'
$newParams = 'parameters="hgw500_eapol_trace=$radio2g_eapol_trace hgw500_eapol_mgnt_queue=$radio2g_eapol_mgnt_queue hgw500_tx_reclaim_poll=1"'

$oldRtl8192eeParams = 'hgw500_force_data_mcs7=1'
$newRtl8192eeParams = 'hgw500_force_data_mcs7=0'

$oldExpect = "hgw500_txbd_be_legacy64=N hgw500_tx_queue_guard=N \`n`t`t`thgw500_txbd_final_readback=N hgw500_tx_reclaim_poll=N; do"
$newExpect = "hgw500_txbd_be_legacy64=N hgw500_tx_queue_guard=N \`n`t`t`thgw500_txbd_final_readback=N hgw500_tx_reclaim_poll=Y; do"

$oldMcsExpect = "hgw500_force_data_mcs7=Y hgw500_force_data_mcs15=N \"
$newMcsExpect = "hgw500_force_data_mcs7=N hgw500_force_data_mcs15=N \"

$oldProfile = "profile=all64-mcs7-eapol-mgntq-q2"
$newProfile = "profile=all64-autorate-eapol-mgntq-reclaim"

foreach ($needle in @($oldParams, $oldRtl8192eeParams, $oldExpect, $oldMcsExpect, $oldProfile)) {
    if (-not $text.Contains($needle)) {
        throw "source loader does not contain expected text: $needle"
    }
}

$patched = $text.Replace($oldParams, $newParams).Replace($oldRtl8192eeParams, $newRtl8192eeParams).Replace($oldExpect, $newExpect).Replace($oldMcsExpect, $newMcsExpect).Replace($oldProfile, $newProfile)
if ($patched -eq $text) {
    throw "patch produced no changes"
}

[IO.File]::WriteAllText($out, $patched, [Text.UTF8Encoding]::new($false))
$patchedSha = (Get-FileHash -Algorithm SHA256 -LiteralPath $out).Hash.ToLowerInvariant()

[ordered]@{
    schema = "openmitrastar.f66-2g-queue-guard-loader/v1"
    created_at = (Get-Date).ToString("o")
    source_loader = [IO.Path]::GetFullPath($SourceLoader)
    source_sha256 = $originalSha
    output_loader = $out
    output_sha256 = $patchedSha
    profile = "all64-autorate-eapol-mgntq-reclaim"
    changes = [ordered]@{
        rtl_pci = @(
            "hgw500_tx_queue_guard remains disabled",
            "hgw500_tx_reclaim_poll=1"
        )
        rtl8192ee = @(
            "hgw500_force_data_mcs7=0",
            "unchanged: hgw500_txbd_be_data_split=1"
        )
    }
    build_env = [ordered]@{
        OM_Q3_RADIO_MODULES_PATH = $out
        OM_Q3_EXPECTED_RADIO_MODULES_SHA256 = $patchedSha
    }
    safety = [ordered]@{
        touches_router = $false
        opens_uart = $false
        flash = $false
        intended_use = "only build a future F66 candidate if F65 boots but AELITA 2.4 throughput is below threshold"
    }
} | ConvertTo-Json -Depth 8 | Set-Content -Encoding ascii -LiteralPath $result

Get-Content -LiteralPath $result -Raw
