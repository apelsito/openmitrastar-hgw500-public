param([Parameter(Mandatory=$true)][string]$ResultPath)
$ErrorActionPreference='Stop';Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot 'f366r3_source_freeze.ps1')
$directory=Join-Path ([IO.Path]::GetTempPath()) ('f366r3-freeze-'+[Guid]::NewGuid().ToString('N'))
[void][IO.Directory]::CreateDirectory($directory)
$source=Join-Path $directory 'source.txt';$planPath=Join-Path $directory 'plan.json';$freeze=$null;$checks=0
try {
    [IO.File]::WriteAllText($source,'test-source')
    $pins=@{};$pins[$source]=(Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant()
    [IO.File]::WriteAllText($planPath,(@{sources=$pins}|ConvertTo-Json -Depth 4))
    $plan=Get-Content -LiteralPath $planPath -Raw|ConvertFrom-Json
    $digest=(Get-FileHash -LiteralPath $planPath -Algorithm SHA256).Hash.ToLowerInvariant()
    $freeze=Enter-F366R3SourceFreeze -PlanPath $planPath -PlanSha256 $digest -Plan $plan
    if($freeze.Count -ne 2 -or [IO.File]::ReadAllText($source) -cne 'test-source'){throw 'READ_OR_HANDLE_COUNT'};$checks++
    foreach($path in @($source,$planPath)){
        $blocked=$false
        try{$writer=[IO.File]::Open($path,[IO.FileMode]::Open,[IO.FileAccess]::Write,[IO.FileShare]::ReadWrite);$writer.Dispose()}catch [IO.IOException]{$blocked=$true}
        if(-not $blocked){throw 'WRITE_NOT_BLOCKED'};$checks++
    }
    $blocked=$false;try{[IO.File]::Delete($source)}catch [IO.IOException]{$blocked=$true}
    if(-not $blocked){throw 'DELETE_NOT_BLOCKED'};$checks++
    Exit-F366R3SourceFreeze -Freeze $freeze
    [IO.File]::WriteAllText($source,'after-release')
    if([IO.File]::ReadAllText($source) -cne 'after-release'){throw 'RELEASE_FAILED'};$checks++
    $freeze=$null
    $failed=$false;try{[void](Enter-F366R3SourceFreeze -PlanPath $planPath -PlanSha256 $digest -Plan $plan)}catch{$failed=$true}
    if(-not $failed){throw 'DRIFT_NOT_REJECTED'}
    [IO.File]::WriteAllText($source,'after-failed-admission');$checks++
    $result=[ordered]@{passed=$true;tests=$checks;hardware_actions=$false;real_local_file_handles=$true}
    [IO.File]::WriteAllText([IO.Path]::GetFullPath($ResultPath),($result|ConvertTo-Json),[Text.UTF8Encoding]::new($false))
    $result|ConvertTo-Json
} finally {
    if($freeze){Exit-F366R3SourceFreeze -Freeze $freeze}
    # Delete only the two explicitly created temporary files and empty folder.
    if([IO.File]::Exists($source)){[IO.File]::Delete($source)}
    if([IO.File]::Exists($planPath)){[IO.File]::Delete($planPath)}
    [IO.Directory]::Delete($directory,$false)
}
