# F321-specific stdin transport override. The sealed F319 helper is unchanged.
# Windows PowerShell 5's Process.StandardInput writer emits a UTF-8 BOM; a
# POSIX shell then sees BOM+grep as the command name. Write explicit LF bytes
# through the underlying pipe instead of that text writer.
function Invoke-F319SshScript {
    param(
        [Parameter(Mandatory = $true)][string]$SshPath,
        [Parameter(Mandatory = $true)][AllowEmptyString()][string[]]$Arguments,
        [Parameter(Mandatory = $true)][string]$Script,
        [ValidateRange(1, 120)][int]$TimeoutSeconds = 45
    )
    $start = [Diagnostics.ProcessStartInfo]::new()
    $start.FileName = $SshPath
    $start.Arguments = (($Arguments | ForEach-Object { ConvertTo-F319NativeArgument $_ }) -join ' ')
    $start.UseShellExecute = $false; $start.CreateNoWindow = $true
    $start.RedirectStandardInput = $true; $start.RedirectStandardOutput = $true; $start.RedirectStandardError = $true
    $process = [Diagnostics.Process]::new(); $process.StartInfo = $start
    $didStart = $false
    try {
        # .NET Framework constructs StandardInput from Console.InputEncoding
        # and AutoFlush emits its preamble during Start, before BaseStream is
        # available. Set a BOM-free encoding for construction, then restore it.
        $previousInputEncoding = [Console]::InputEncoding
        try {
            [Console]::InputEncoding = [Text.UTF8Encoding]::new($false)
            if (-not $process.Start()) { throw 'Could not start the bounded SSH process' }
            $didStart = $true
        } finally { [Console]::InputEncoding = $previousInputEncoding }
        $stdoutTask = $process.StandardOutput.ReadToEndAsync()
        $stderrTask = $process.StandardError.ReadToEndAsync()
        $payload = [Text.UTF8Encoding]::new($false).GetBytes($Script.Replace("`r`n", "`n") + "`n")
        $inputPipe = $process.StandardInput.BaseStream
        $inputPipe.Write($payload, 0, $payload.Length)
        $inputPipe.Flush()
        $inputPipe.Close()
        if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
            $process.Kill(); [void]$process.WaitForExit(3000)
            throw 'SSH script timed out; runtime outcome is unproven'
        }
        if (-not [Threading.Tasks.Task]::WaitAll([Threading.Tasks.Task[]]@($stdoutTask,$stderrTask),5000)) {
            throw 'SSH output pipes did not close; runtime outcome is unproven'
        }
        return [pscustomobject]@{ExitCode=$process.ExitCode;Stdout=$stdoutTask.GetAwaiter().GetResult();Stderr=$stderrTask.GetAwaiter().GetResult()}
    } finally {
        try {
            if ($didStart -and -not $process.HasExited) { $process.Kill(); [void]$process.WaitForExit(3000) }
        } finally { $process.Dispose() }
    }
}
