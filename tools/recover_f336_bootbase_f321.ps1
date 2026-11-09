[CmdletBinding(PositionalBinding=$false)]
param([Parameter(Mandatory=$true)][string]$PlanPath,[Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{64}$')][string]$PlanSha256,[switch]$Execute)
$ErrorActionPreference='Stop';Set-StrictMode -Version Latest
if((Get-FileHash -LiteralPath $PlanPath -Algorithm SHA256).Hash.ToLowerInvariant() -cne $PlanSha256){throw 'RECOVERY_PLAN_HASH'}
$p=Get-Content -LiteralPath $PlanPath -Raw | ConvertFrom-Json
if($p.schema -cne 'openmitrastar.f336-bootbase-recovery/v1' -or $p.origin_run -cne 'f336-ram-20260921T132233Z-03826f49' -or $p.flash_writes_allowed -ne $false){throw 'RECOVERY_SCOPE'}
foreach($file in $p.sources.PSObject.Properties){if((Get-FileHash -LiteralPath $file.Name -Algorithm SHA256).Hash.ToLowerInvariant() -cne $file.Value){throw 'RECOVERY_SOURCE_DRIFT'}}
if(-not $Execute){[pscustomobject]@{status='OFFLINE_ONLY';hardware_actions=$false;requires_ssh=$false}|ConvertTo-Json;return}
. (Join-Path $PSScriptRoot 'f319_uart_guard.ps1')
$dir=Join-Path (Split-Path -Parent $PSScriptRoot) ('outputs\recovery\f336-bootbase-'+[DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')+'-'+[Guid]::NewGuid().ToString('N').Substring(0,8))
[void](New-Item -ItemType Directory -Path $dir);$guard=$null;$launched=$false;$old=$env:OM_F336_BOOTBASE_RECOVERY
try {
    $guard=Enter-F319HardwareGuard -Port COM3 -ExpectedPnpDeviceId 'FTDIBUS\VID_0403+PID_6001+AG41W2BLA\0000' -PhysicalLockDir (Join-Path (Split-Path -Parent $PSScriptRoot) 'outputs/locks/f301-physical-radio.lock') -Owner 'F336_DIRECT_F321_RECOVERY' -EvidenceDir $dir
    $c=[ordered]@{schema='openmitrastar.f336-bootbase-recovery-context/v1';purpose='direct-f321-return-no-ssh';origin_run=$p.origin_run;fresh_ssh_binding=$false;
      plan_path=[IO.Path]::GetFullPath($PlanPath);plan_sha256=$PlanSha256;expires_at_utc=[DateTimeOffset]::UtcNow.AddMinutes(15).ToString('o');owner_pid=$guard.OwnerPid;owner_start_ticks=$guard.OwnerStartTicks;lease_token=$guard.LeaseToken;physical_lock_dir=$guard.PhysicalLockDir;uart_pnp_device_id=$guard.PnpDeviceId}
    $env:OM_F336_BOOTBASE_RECOVERY=$c|ConvertTo-Json -Compress
    $launched=$true;& $p.python_executable (Join-Path $PSScriptRoot 'recover_f336_bootbase_f321.py') --execute --plan $PlanPath --plan-sha256 $PlanSha256 --output-dir $dir
    if($LASTEXITCODE -ne 0){throw 'RECOVERY_NOT_CONFIRMED'}
} finally {
    $env:OM_F336_BOOTBASE_RECOVERY=$old
    if($guard){
        $contained=-not $launched;$resultPath=Join-Path $dir 'result.json'
        if(Test-Path -LiteralPath $resultPath){$r=Get-Content -LiteralPath $resultPath -Raw|ConvertFrom-Json;$contained=$r.containment_confirmed -is [bool] -and $r.containment_confirmed}
        if($contained){Exit-F319HardwareGuard -Guard $guard}else{Write-Warning 'F336 recovery lock directory retained: containment unproven'}
    }
}
