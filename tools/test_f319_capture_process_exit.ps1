[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][ValidateSet('legacy','retained')][string]$Mode,
    [Parameter(Mandatory=$true)][string]$OutputDir,
    [ValidateSet(0,7)][int]$ChildExitCode=0
)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
if(Test-Path -LiteralPath $OutputDir){throw 'Refuse to replace process-test evidence'}
New-Item -ItemType Directory -Path $OutputDir|Out-Null
$engine=(Get-Process -Id $PID).Path
$command='[Console]::Out.WriteLine("F319_SYNTHETIC_CHILD"); Start-Sleep -Milliseconds 300; exit '+$ChildExitCode
$encoded=[Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($command))
$child=$null
try {
    $child=Start-Process -FilePath $engine -WindowStyle Hidden -ArgumentList @('-NoProfile','-NonInteractive','-EncodedCommand',$encoded) -RedirectStandardOutput (Join-Path $OutputDir 'child.stdout.log') -RedirectStandardError (Join-Path $OutputDir 'child.stderr.log') -PassThru
    if($Mode -eq 'retained'){[void]$child.Handle}
    $finished=$child.WaitForExit(10000)
    if(-not $finished){throw 'Synthetic child timed out'}
    $child.Refresh()
    $result=[ordered]@{mode=$Mode;engine=$PSVersionTable.PSVersion.ToString();pid=$child.Id;has_exited=$child.HasExited;expected_exit_code=$ChildExitCode;exit_code=$child.ExitCode;exit_code_is_int=($child.ExitCode -is [int]);hardware_actions=$false}
    $json=$result|ConvertTo-Json
    $json|Set-Content -LiteralPath (Join-Path $OutputDir 'result.json') -Encoding ascii
    $json
} finally {
    if($child){if(-not $child.HasExited){$child.Kill();[void]$child.WaitForExit(3000)};$child.Dispose()}
}
