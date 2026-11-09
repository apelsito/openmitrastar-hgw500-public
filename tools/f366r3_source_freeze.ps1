Set-StrictMode -Version Latest

function Enter-F366R3SourceFreeze {
    param([Parameter(Mandatory=$true)][string]$PlanPath,
          [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{64}$')][string]$PlanSha256,
          [Parameter(Mandatory=$true)]$Plan)
    $handles=[System.Collections.Generic.List[System.IO.FileStream]]::new()
    $fullPlan=[IO.Path]::GetFullPath($PlanPath)
    try {
        $paths=@($fullPlan)+@($Plan.sources.PSObject.Properties | ForEach-Object { [IO.Path]::GetFullPath($_.Name) })
        $paths=@($paths | Sort-Object -Unique)
        foreach($path in $paths){
            $handle=[IO.File]::Open($path,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::Read)
            $handles.Add($handle)
        }
        if((Get-FileHash -LiteralPath $fullPlan -Algorithm SHA256).Hash.ToLowerInvariant() -cne $PlanSha256){throw 'F366R3_FROZEN_PLAN_DRIFT'}
        foreach($entry in $Plan.sources.PSObject.Properties){
            if((Get-FileHash -LiteralPath $entry.Name -Algorithm SHA256).Hash.ToLowerInvariant() -cne $entry.Value){throw 'F366R3_FROZEN_SOURCE_DRIFT'}
        }
        return [pscustomobject]@{Handles=$handles;Count=$handles.Count;PlanPath=$fullPlan;Closed=$false}
    } catch {
        for($i=$handles.Count-1;$i -ge 0;$i--){$handles[$i].Dispose()}
        throw
    }
}

function Exit-F366R3SourceFreeze {
    param([Parameter(Mandatory=$true)]$Freeze)
    if(-not $Freeze.Closed){
        for($i=$Freeze.Handles.Count-1;$i -ge 0;$i--){$Freeze.Handles[$i].Dispose()}
        $Freeze.Closed=$true
    }
}
