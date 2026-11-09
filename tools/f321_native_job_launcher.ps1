[CmdletBinding(PositionalBinding = $false)]
param([Parameter(Mandatory=$true)][string]$JobName,
      [Parameter(Mandatory=$true)][string]$Program,
      [Parameter(Mandatory=$true)][string]$ArgumentsBase64)
$ErrorActionPreference = 'Stop'
Add-Type -Path (Join-Path $PSScriptRoot 'f321_process_job.cs')
[F321ProcessJob]::JoinCurrentProcess($JobName)
# The native process cannot start unless the parent-owned job already contains
# this launcher. The job remains alive in the parent until all descendants exit.
$nativeArguments = @([Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($ArgumentsBase64)) | ConvertFrom-Json)
$OutputEncoding = [Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$ErrorActionPreference = 'Continue'
& $Program @nativeArguments
exit $LASTEXITCODE
