param(
    [string]$Stamp = (Get-Date -Format 'yyyyMMdd-HHmmss')
)

$ErrorActionPreference = 'Stop'

$repo = (Get-Location).Path
$root = Join-Path $repo "outputs\driver-bundles\openmitrastar-hgw500-radio-drivers-latest-$Stamp"
$zip = "$root.zip"

function Copy-PathInto {
    param(
        [Parameter(Mandatory=$true)][string]$Source,
        [Parameter(Mandatory=$true)][string]$Destination
    )

    if (Test-Path -LiteralPath $Source -PathType Container) {
        if (Test-Path -LiteralPath $Destination) {
            Remove-Item -LiteralPath $Destination -Recurse -Force
        }
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Destination) | Out-Null
        Copy-Item -LiteralPath $Source -Destination $Destination -Recurse -Force
    } elseif (Test-Path -LiteralPath $Source -PathType Leaf) {
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Destination) | Out-Null
        Copy-Item -LiteralPath $Source -Destination $Destination -Force
    } else {
        Write-Host "SKIP missing $Source"
    }
}

function Write-TextFile {
    param(
        [Parameter(Mandatory=$true)][string]$Path,
        [Parameter(Mandatory=$true)][string]$Text
    )
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Path) | Out-Null
    Set-Content -LiteralPath $Path -Value $Text -Encoding UTF8
}

if (Test-Path -LiteralPath $root) {
    Remove-Item -LiteralPath $root -Recurse -Force
}
if (Test-Path -LiteralPath $zip) {
    Remove-Item -LiteralPath $zip -Force
}
if (Test-Path -LiteralPath "$zip.sha256") {
    Remove-Item -LiteralPath "$zip.sha256" -Force
}

New-Item -ItemType Directory -Force -Path $root | Out-Null

Copy-PathInto '.\outputs\kernel-port\realtek-loop\eapol-mgntq-v1-RAM-ONLY-NO-FLASH' `
    (Join-Path $root 'drivers\2g-realtek\artifact-eapol-mgntq-v1-RAM-ONLY-NO-FLASH')
Copy-PathInto '.\work\kernel-port\linux-5.10\drivers\net\wireless\realtek\rtlwifi' `
    (Join-Path $root 'drivers\2g-realtek\source-rtlwifi-linux-5.10')
New-Item -ItemType Directory -Force -Path (Join-Path $root 'drivers\2g-realtek\patches') | Out-Null
Get-ChildItem -LiteralPath '.\work\kernel-port\linux-5.10' -Filter 'rtlwifi-*.patch' -File | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $root 'drivers\2g-realtek\patches') -Force
}
Copy-PathInto '.\work\linux510-radio-port\realtek\firmware' `
    (Join-Path $root 'drivers\2g-realtek\firmware-source')
Copy-PathInto '.\work\linux510-radio-port\realtek\netqueue-diag' `
    (Join-Path $root 'drivers\2g-realtek\netqueue-diag-source')

Copy-PathInto '.\outputs\kernel-port\quantenna-5g-v6.1-scheduler-contract-20260824' `
    (Join-Path $root 'drivers\5g-quantenna\artifact-v6.1-scheduler-contract-20260824')
Copy-PathInto '.\outputs\kernel-port\quantenna-5g-v6.2-scheduler-diag-uafsafe-package-20260824' `
    (Join-Path $root 'drivers\5g-quantenna\artifact-v6.2-scheduler-diag-uafsafe-20260824')
Copy-PathInto '.\outputs\kernel-port\quantenna-5g-v6-scheduler-diag' `
    (Join-Path $root 'drivers\5g-quantenna\artifact-v6-scheduler-diag')
Copy-PathInto '.\work\linux510-radio-port\quantenna-v6-scheduler-diag' `
    (Join-Path $root 'drivers\5g-quantenna\source-quantenna-v6-scheduler-diag')
Copy-PathInto '.\outputs\kernel-port\quantenna-5g-offline-audit-20260824' `
    (Join-Path $root 'drivers\5g-quantenna\offline-audit-20260824')
Copy-PathInto '.\outputs\kernel-port\quantenna-5g-auc-muc-oob-v5-20260823' `
    (Join-Path $root 'drivers\5g-quantenna\previous-v5-auc-muc-oob-20260823')

Copy-PathInto '.\work\mission-state\w4-rootfs-product\build' `
    (Join-Path $root 'product-rootfs\w4-product-rootfs-build-NO-FLASH')
Copy-PathInto '.\work\mission-state\f5-autonomous-gzipinit\build' `
    (Join-Path $root 'product-rootfs\f5-autonomous-gzipinit-build-NO-FLASH')
Copy-PathInto '.\work\mission-state\f5-safe2g-emacrxrestart-gzipinit\build' `
    (Join-Path $root 'product-rootfs\f38-safe2g-emacrxrestart-build')
Copy-PathInto '.\work\tftp\omvl\openmitrastar-linux510-f5-safe2g-emacrxrestart-gzipinit-v1.webformat.bin' `
    (Join-Path $root 'product-rootfs\f38-safe2g-emacrxrestart-image\openmitrastar-linux510-f5-safe2g-emacrxrestart-gzipinit-v1.webformat.bin')

$docs = @(
    '.\work\mission-state\AELITA_WIFI_PORTING_STATUS_20260824.md',
    '.\work\mission-state\F38_FLASH_WATCH_STATUS_20260825_1516.md',
    '.\work\mission-state\QTN_5G_OFFLINE_AUDIT_20260824.md',
    '.\work\mission-state\V5_OFFLINE_RESULT_20260823.md',
    '.\outputs\handoffs\AELITA_OPENMITRASTAR_HANDOFF_20260823.md',
    '.\outputs\handoffs\OPENMITRASTAR_DUAL_RADIO_PORT_AI_HANDOFF_PROMPT.md',
    '.\docs\HGW500_LINUX510_SSH_DIAGNOSTIC_20260824.md',
    '.\docs\DRIVER_REVERSE_ENGINEERING_STATUS.md',
    '.\docs\HGW500_Q1_CONTROLS_PARITY_20260820.md',
    '/workspace/user-home\Downloads\OpenMitraStar_Linux510_Dual_Radio_Port_Audit_20260824.md'
)
New-Item -ItemType Directory -Force -Path (Join-Path $root 'docs') | Out-Null
foreach ($doc in $docs) {
    if (Test-Path -LiteralPath $doc) {
        Copy-Item -LiteralPath $doc -Destination (Join-Path $root 'docs') -Force
    } else {
        Write-Host "SKIP missing $doc"
    }
}

$toolFiles = @(
    '.\tools\run_aelita_2g_wpa2_runtime_psk_once.py',
    '.\tools\run_aelita_2g_wpa2_mgmt_trace_hotload_once.py',
    '.\tools\run_aelita_2g_wpa2_hostapd_variant_once.py',
    '.\tools\test_aelita_2g_mgmt_trace_hotload.py',
    '.\tools\test_aelita_2g_wpa2_runtime_psk_once.py',
    '.\tools\test_w2_all64_autorate_hotload.py',
    '.\tools\test_qtn_5g_v61_scheduler_contract.py',
    '.\tools\qtn_5g_v62_scheduler_contract.py',
    '.\tools\test_qtn_5g_v62_scheduler_contract.py',
    '.\tools\test_qtn_5g_v6_scheduler_diag.py',
    '.\tools\build_qtn_5g_v62_scheduler_diag_uafsafe.py',
    '.\tools\wait_f38_flash_or_action.ps1',
    '.\tools\run_f38_to_dual_radio_pipeline.ps1',
    '.\tools\run_2g_queue_guard_after_f38_low.ps1',
    '.\tools\run_qtn_5g_after_f38_ready.ps1',
    '.\tools\aelita_f38_ops_status.ps1',
    '.\tools\triage_f38_postflash.ps1',
    '.\tools\diagnose_hgw500_ssh_management.py',
    '.\tools\test_diagnose_hgw500_ssh_management.py',
    '.\tools\test_qtn_5g_aelita_one_shot.py',
    '.\tools\test_qtn_5g_aelita_uart_capture.py',
    '.\tools\test_evaluate_qtn_5g_uart_txpath.py',
    '.\tools\evaluate_qtn_5g_uart_txpath.py'
)
New-Item -ItemType Directory -Force -Path (Join-Path $root 'tools') | Out-Null
foreach ($tool in $toolFiles) {
    if (Test-Path -LiteralPath $tool) {
        Copy-Item -LiteralPath $tool -Destination (Join-Path $root 'tools') -Force
    } else {
        Write-Host "SKIP missing $tool"
    }
}

Copy-PathInto '.\Accesos.txt' (Join-Path $root 'private\credentials\Accesos.txt')
Copy-PathInto '.\work\secrets-backup' (Join-Path $root 'private\credentials\work-secrets-backup')

$readme = @"
# OpenMitraStar HGW-500BNA-QCv2 Radio Drivers Bundle

Date: 2026-08-25
Target: MitraStar HGW-500BNA-QCv2 / ARC700 / Linux 5.10.260-openmitrastar-radiohw

## Contents

- drivers/2g-realtek: latest Realtek RTL8192EE 2.4 GHz Linux 5.10 work tree, binary RAM-only diagnostic artifact, firmware, patches and tests.
- drivers/5g-quantenna: latest Quantenna 5 GHz qdrv v6.2 UAF-safe scheduler diagnostic artifact, v6/v6.1 historical scheduler artifacts, source tree, prior v5 package and offline audit.
- docs: current porting status, 5 GHz audit, v5 result and handoff docs.
- product-rootfs: current W4 product-rootfs, F5 review build, and F38 safe2g EMAC RX restart image/build outputs.
- tools: focused test/oracle runners used for AELITA and 5 GHz UART/OOB diagnostics.
- private/credentials: local owner-provided HGW-500 access/config material. Treat this folder as private.

## Current Status Summary

F38 flash state: `f5-safe2g-emacrxrestart` is armed for `mtd4/linux_live` via the existing COM3 watcher, but at bundle time F38 had not started writing because Bootbase had not appeared. The watcher classification was `WAITING_PHYSICAL_POWER_CYCLE_OLD_EMAC_FREEZE`.

2.4 GHz: previous F5/F38-adjacent live evidence proved association and HTTP traffic around 7.5-7.9 Mbps before the current EMAC stall. F38 postflash gate requires at least 5 Mbps and captures BE queue/rate evidence if throughput is low. The next low-risk 2.4 discriminator after stable SSH is BE queue guard plus reclaim-poll, not blind fixed-rate tuning.

5 GHz: not product-ready. Latest default diagnostic path is v6.2 UAF-safe scheduler diagnostic (`qdrv` SHA256 `5b9ae80e5121c4b00965ce4716ad80285f1b599e29845e8efbf938a79600df35`). It preserves AUTH/ASSOC TX-path correlation by skb and hd_pa while avoiding the enqueue-result trace use-after-free found in v6. It does not change queues, DMA, forwarding, rates, rings or firmware blobs. `run_qtn_5g_after_f38_ready.ps1` refuses to start 5 GHz until F38 postflash triage returns `READY_2G_PASS`.

## Safety

Do not flash driver artifacts directly. F38 is the only current flash candidate in this bundle context and targets `mtd4/linux_live` through the existing Bootbase watcher; the 2.4 and 5 GHz driver artifacts remain review/diagnostic material unless promoted by later gates.

The included F5/product-rootfs artifacts are review context. At packaging time their manifests still report candidate_eligible=false and flash_supported=false.

## Verification

Use SHA256SUMS at the bundle root to verify every file in this archive.
"@
Write-TextFile (Join-Path $root 'README.md') $readme
Write-TextFile (Join-Path $root 'private\README-PRIVATE.md') 'This directory contains owner-requested private credential/config material. Do not publish or paste contents in chat.'

$hashPath = Join-Path $root 'SHA256SUMS'
Push-Location $root
try {
    Get-ChildItem -Recurse -File | Sort-Object FullName | ForEach-Object {
        $rel = Resolve-Path -LiteralPath $_.FullName -Relative
        $rel = $rel -replace '^\.\\','' -replace '\\','/'
        $hash = Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256
        '{0}  {1}' -f $hash.Hash.ToLowerInvariant(), $rel
    } | Set-Content -LiteralPath $hashPath -Encoding ASCII
} finally {
    Pop-Location
}

Compress-Archive -LiteralPath $root -DestinationPath $zip -CompressionLevel Optimal
$zipHash = Get-FileHash -LiteralPath $zip -Algorithm SHA256
$zipHash.Hash.ToLowerInvariant() | Set-Content -LiteralPath "$zip.sha256" -Encoding ASCII

[PSCustomObject]@{
    bundle = $root
    zip = $zip
    zip_sha256 = $zipHash.Hash.ToLowerInvariant()
    zip_bytes = (Get-Item -LiteralPath $zip).Length
    file_count = (Get-ChildItem -LiteralPath $root -Recurse -File).Count
} | ConvertTo-Json -Depth 3
