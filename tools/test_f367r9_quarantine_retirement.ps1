[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$OutputDir)
$ErrorActionPreference='Stop';Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot 'f319_uart_guard.ps1')
. (Join-Path $PSScriptRoot 'f367r9_return_context.ps1')
$root=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$out=Assert-R9ReturnPath $OutputDir -MayNotExist
if(-not $out.StartsWith((Join-Path $root 'outputs\preflight\'),[StringComparison]::OrdinalIgnoreCase) -or (Test-Path -LiteralPath $out)){throw 'NEW_SCOPED_TEST_DIR_REQUIRED'}
[void](New-Item -ItemType Directory -Path $out)
$parent=Join-Path $out 'synthetic-parent.lock';$archive=Join-Path $out 'synthetic-retired-quarantine'
$child=Join-Path $parent 'r9-return-f365.lock'
[void](New-Item -ItemType Directory -Path $child)
$owner=Join-Path $parent 'owner.json';$claim=Join-Path $parent 'r9-return-attempt.json'
[IO.File]::WriteAllText($owner,'{"fixture":"preserve exact parent bytes"}',[Text.UTF8Encoding]::new($false))
[IO.File]::WriteAllText($claim,'{"fixture":"preserve attempt"}',[Text.UTF8Encoding]::new($false))
$ownerHash=(Get-FileHash -LiteralPath $owner -Algorithm SHA256).Hash.ToLowerInvariant()
$claimHash=(Get-FileHash -LiteralPath $claim -Algorithm SHA256).Hash.ToLowerInvariant()
$parentStream=[IO.File]::Open($owner,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::Read)
$token=[Guid]::NewGuid().ToString('N')
$childPath=Join-Path $child 'owner.json'
[IO.File]::WriteAllText($childPath,(@{lease_token=$token;pid=$PID}|ConvertTo-Json),[Text.UTF8Encoding]::new($false))
$stream=[IO.File]::Open($childPath,[IO.FileMode]::Open,[IO.FileAccess]::ReadWrite,[IO.FileShare]::Read)
$names=@(('Local\R9SyntheticTestA-'+$token),('Local\R9SyntheticTestB-'+$token))
$mutexes=@();$guard=$null
try {
    foreach($name in $names){$mutex=[Threading.Mutex]::new($false,$name);if(-not $mutex.WaitOne(0)){throw 'FIXTURE_MUTEX'};$mutexes+=$mutex}
    $guard=[pscustomobject]@{PhysicalLockDir=$child;OwnedMutexes=$mutexes;OwnsPhysicalLock=$true;LeaseStream=$stream;LeaseToken=$token}
    $pass=[pscustomobject]@{status='PASS_R9_EXACT_F365_RETURN';f365_return_confirmed=$true;containment_confirmed=$true;retain_lease_required=$false;flash_command_in_flight=$false}
    $fail=[pscustomobject]@{status='FAILED_RETURN_NO_RETRY';f365_return_confirmed=$false;containment_confirmed=$true;retain_lease_required=$true;flash_command_in_flight=$false}
    $rejected=$false
    try{[void](Move-R9VerifiedQuarantine -Guard $guard -Parent $parent -Archive $archive -OwnerSha256 $ownerHash -ParentStream $parentStream -Result $fail)}catch{$rejected=$_.Exception.Message -ceq 'R9_ARCHIVE_REQUIRES_COMPLETE_RETURN'}
    if(-not $rejected -or -not (Test-Path -LiteralPath $owner) -or -not (Test-Path -LiteralPath $childPath)){throw 'FAILURE_DID_NOT_PRESERVE_QUARANTINE'}
    [void](Move-R9VerifiedQuarantine -Guard $guard -Parent $parent -Archive $archive -OwnerSha256 $ownerHash -ParentStream $parentStream -Result $pass)
    if(Test-Path -LiteralPath $parent){throw 'PARENT_NOT_RETIRED'}
    if((Get-FileHash -LiteralPath (Join-Path $archive 'owner.json') -Algorithm SHA256).Hash.ToLowerInvariant() -cne $ownerHash -or
       (Get-FileHash -LiteralPath (Join-Path $archive 'r9-return-attempt.json') -Algorithm SHA256).Hash.ToLowerInvariant() -cne $claimHash){throw 'METADATA_NOT_PRESERVED'}
    # Verify a separate process cannot acquire either mutex after the rename.
    # Uses unique synthetic mutex names, never the real HGW mutex namespace.
    $probe=Join-Path $out 'mutex-probe.ps1'
    @'
param([string]$Name)
$m=[Threading.Mutex]::OpenExisting($Name)
$acquired=$false
try{$acquired=$m.WaitOne(0);if($acquired){exit 2};'HELD_BY_PARENT'}finally{if($acquired){$m.ReleaseMutex()};$m.Dispose()}
'@ | Set-Content -LiteralPath $probe -Encoding ASCII
    foreach($name in $names){$observed=& (Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe') -NoProfile -NonInteractive -File $probe -Name $name;if($LASTEXITCODE -ne 0 -or $observed -cne 'HELD_BY_PARENT'){throw 'EXCLUSION_LOST_DURING_RETIREMENT'}}
    $pins=@{}
    foreach($name in @('test_f367r9_quarantine_retirement.ps1','f367r9_return_context.ps1','f319_uart_guard.ps1')){$file=Join-Path $PSScriptRoot $name;$pins[$file]=(Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant()}
    $result=@{status='PASS_R9_SYNTHETIC_QUARANTINE_RETIREMENT';checks=6;hardware_actions=$false;real_mutexes_used=$false;metadata_preserved=$true;both_mutexes_held_after_move=$true;recursive_deletion=$false;source_pins=$pins}
    [IO.File]::WriteAllText((Join-Path $out 'result.json'),($result|ConvertTo-Json),[Text.UTF8Encoding]::new($false))
    $result|ConvertTo-Json
}finally{
    if($guard -and $guard.LeaseStream){$guard.LeaseStream.Dispose()}elseif($stream){$stream.Dispose()}
    $parentStream.Dispose()
    foreach($mutex in $mutexes){$mutex.ReleaseMutex();$mutex.Dispose()}
}
