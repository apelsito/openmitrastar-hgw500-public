Set-StrictMode -Version Latest

function Get-F319VerifiedRecoveryRehearsal {
    param([Parameter(Mandatory = $true)][string]$ResultPath)
    $path = [IO.Path]::GetFullPath($ResultPath)
    $directory = Split-Path -Parent $path
    $result = Get-Content -LiteralPath $path -Raw | ConvertFrom-Json
    $restorePath = Join-Path $directory 'f314-restore/result.json'
    $platformPath = Join-Path $directory 'postflash-f314/status.json'
    $restore = Get-Content -LiteralPath $restorePath -Raw | ConvertFrom-Json
    $platform = Get-Content -LiteralPath $platformPath -Raw | ConvertFrom-Json
    $sha = 'a0c7350a50e5e4b532a0202982e6cd3c2d3da4e2e91079cd105473b248523f11'
    if ($result.schema -ne 'openmitrastar.f319-bootbase-recovery-rehearsal-result/v1' -or
        $result.status -ne 'PASS_F314_RESTORE_WITHOUT_SSH_IN_BOOTBASE' -or
        $result.f314_sha256 -ne $sha -or $result.full_slot_crc32 -ne 'd6b13baa' -or
        $result.restore_ssh_dependency -ne $false -or $result.flash_attempted -ne $true -or
        $result.protected_partitions_written -ne $false -or $result.final_binding.NonceObserved -ne $true -or
        $result.final_binding.RouterHost -ne '192.168.1.90' -or
        $result.final_binding.ExpectedVersion -ne 'lyoko-foundation-6.8.2-f314-qtn-nondfs-guard-device' -or
        $result.final_binding.PnpDeviceId -ine 'FTDIBUS\VID_0403+PID_6001+AG41W2BLA\0000' -or
        $restore.status -ne 'PASS' -or $restore.candidate_sha256 -ne $sha -or
        $restore.physical_write.partition -ne 'mtd4/linux_live' -or
        $restore.physical_write.offset -ne 0x007e0000 -or $restore.physical_write.slot_size -ne 0x007a0000 -or
        $restore.readback.full_slot_crc32 -ne 'd6b13baa' -or
        $restore.readback.candidate_prefix_compare -ne 'PASS' -or
        $restore.protected_partitions.status -ne 'PASS' -or $platform.status -ne 'PASS' -or
        $platform.schema -ne 'openmitrastar.f214-device-postflash/v1' -or $platform.host -ne '192.168.1.90' -or
        @($platform.checks.PSObject.Properties | Where-Object { $_.Value -ne $true }).Count -ne 0) {
        throw 'No verified exact F314 Bootbase recovery rehearsal'
    }
    foreach ($requiredCheck in @('ssh_pinned_identity','kernel','release','boot_ready','radio2_ready','radio5_ready','no_fatal')) {
        if ($platform.checks.$requiredCheck -isnot [bool] -or $platform.checks.$requiredCheck -ne $true) {
            throw 'Recovery platform evidence lacks a required live check'
        }
    }
    # Verify every underlying writer transcript against its recorded digest.
    $workspace = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
    foreach ($evidence in @($restore.evidence)) {
        $evidencePath = if ([IO.Path]::IsPathRooted($evidence.path)) { $evidence.path } else { Join-Path $workspace $evidence.path }
        $stream = [IO.File]::OpenRead($evidencePath)
        try {
            $digest = [Security.Cryptography.SHA256]::Create()
            try { $actual = ([BitConverter]::ToString($digest.ComputeHash($stream))).Replace('-', '').ToLowerInvariant() }
            finally { $digest.Dispose() }
        } finally { $stream.Dispose() }
        if ($actual -cne $evidence.sha256) { throw 'Recovery rehearsal transcript changed' }
    }
    if (@($restore.evidence).Count -lt 5) { throw 'Recovery rehearsal lacks UART/transport transcripts' }
    return [pscustomobject]@{ResultPath=$path;F314Sha256=$sha;RestorePath=$restorePath;PlatformPath=$platformPath;
        Scope='Bootbase self-restore proven; not proof of recovery from a hard CPU lockup or partial erase failure'}
}

function Assert-F319BorrowedRecoveryGuard {
    param(
        [Parameter(Mandatory = $true)][object]$Guard,
        [Parameter(Mandatory = $true)][object]$BindingProof,
        [Parameter(Mandatory = $true)][string]$Port,
        [Parameter(Mandatory = $true)][string]$ExpectedPnpDeviceId
    )
    # This API is in-process only. A saved readiness JSON or another process's
    # lease cannot substitute for the promoter's still-held hardware ownership.
    if ($Guard.OwnerPid -ne $PID -or $BindingProof.OwnerPid -ne $PID -or
        $Guard.OwnerStartTicks -ne $BindingProof.OwnerStartTicks -or
        $Guard.LeaseToken -cne $BindingProof.LeaseToken -or
        $null -eq $Guard.LeaseStream -or -not $Guard.LeaseStream.CanWrite -or
        $BindingProof.Binding.NonceObserved -isnot [bool] -or $BindingProof.Binding.NonceObserved -ne $true -or
        $BindingProof.Binding.RouterHost -ne '192.168.1.90' -or
        $BindingProof.Binding.ExpectedVersion -ne 'lyoko-foundation-6.8.2-f314-qtn-nondfs-guard-device' -or
        $BindingProof.Binding.Port -ine $Port -or $BindingProof.Binding.PnpDeviceId -ine $ExpectedPnpDeviceId) {
        throw 'Recovery requires the same live in-process guard and its original authenticated HGW binding'
    }
    [void](Assert-F319HardwareLease -PhysicalLockDir $Guard.PhysicalLockDir -OwnerPid $Guard.OwnerPid -OwnerStartTicks $Guard.OwnerStartTicks -LeaseToken $Guard.LeaseToken -Port $Port -ExpectedPnpDeviceId $ExpectedPnpDeviceId)
    return $Guard
}
