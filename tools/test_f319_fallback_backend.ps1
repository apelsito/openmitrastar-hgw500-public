[CmdletBinding()]
param([ValidateSet('success', 'abort', 'prompt-lost')][string]$Case)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$path = Join-Path $PSScriptRoot 'q3_f45_radio5_powerselect_nonfatal_openlab_autostart_mtd4_bootbase_flash.ps1'
$tokens = $null; $errors = $null
$ast = [Management.Automation.Language.Parser]::ParseFile($path, [ref]$tokens, [ref]$errors)
if ($errors.Count) { throw 'Backend source does not parse' }
$function = @($ast.FindAll({param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Receive-CandidateTftp'}, $true))
if ($function.Count -ne 1) { throw 'Transfer function is not unique' }
# Extract this function only; the backend entrypoint and all hardware APIs are never run.
Invoke-Expression $function[0].Extent.Text
$AttemptId = '0123456789abcdef0123456789abcdef'
$ExpectedSha256 = 'a' * 64
$CurrentLiveCrc32 = 'd6b13baa'
$ExpectedBytes = 5292032
$LoadAddress = [uint32]2197815296
$Candidate = 'synthetic-candidate.bin'
$ServerIp = '192.0.2.1'
$sent = [Collections.Generic.List[string]]::new()
$serial = [pscustomobject]@{Messages=[Collections.Generic.List[string]]::new()}
$serial | Add-Member -MemberType ScriptMethod -Name Write -Value {param($text) $this.Messages.Add($text)}
function Send-Uart([string]$Text) { $sent.Add($Text) }
function Wait-Uart([string]$Pattern, [string]$Stage, [int]$Seconds) {
    if ($Case -eq 'success') { return 'synthetic transfer complete' }
    throw 'synthetic transfer timeout'
}
function Wait-Prompt([string]$Stage, [int]$Seconds) {
    if ($Case -eq 'prompt-lost') { throw 'synthetic prompt unavailable' }
    return 'topaz>'
}
function Wait-BootbaseNetwork([string]$Address, [int]$Attempts) { return $true }
function Start-Sleep([int]$Milliseconds, [int]$Seconds) {}
$thrown = $false
$messages = @(& {try { Receive-CandidateTftp } catch { $script:thrown = $true }})
$calls = @($ast.FindAll({param($node) $node -is [Management.Automation.Language.CommandAst] -and $node.GetCommandName() -eq 'Receive-CandidateTftp'}, $true))
@{case=$Case;thrown=$thrown;messages=$messages;sent=@($sent.ToArray());serial_writes=@($serial.Messages.ToArray());
    production_transfer_call_count=$calls.Count;hardware_actions=$false} | ConvertTo-Json -Depth 5
