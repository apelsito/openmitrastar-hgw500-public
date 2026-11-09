# F325-only override of F321's BOM-free, LF-byte stdin transport.
# An uncertain exit remains sticky for the whole physical cycle, including any
# later successful helper. The controller must retain its lease when it is set.
if (-not (Get-Variable -Name F325SshContainmentFailed -Scope Script -ErrorAction SilentlyContinue)) {
    $script:F325SshContainmentFailed = $false
}

function Stop-F325SshProcess {
    param(
        [Parameter(Mandatory = $true)][object]$Process,
        [Parameter(Mandatory = $true)][bool]$Started,
        [ValidateRange(1, 10000)][int]$TimeoutMilliseconds = 3000
    )
    if (-not $Started) { return }
    try {
        if (-not $Process.HasExited) {
            $Process.Kill()
            if (-not $Process.WaitForExit($TimeoutMilliseconds)) {
                throw 'SSH process termination wait expired'
            }
        }
        if (-not $Process.HasExited) { throw 'SSH process exit is unproven' }
    } catch {
        $script:F325SshContainmentFailed = $true
        throw 'F325 SSH process exit could not be proved; retain the physical lease'
    }
}

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
        # Framework's StandardInput constructor uses Console.InputEncoding and
        # can emit its BOM before BaseStream becomes available.
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
            Stop-F325SshProcess -Process $process -Started $didStart
            throw 'SSH script timed out; runtime outcome is unproven'
        }
        if (-not [Threading.Tasks.Task]::WaitAll([Threading.Tasks.Task[]]@($stdoutTask, $stderrTask), 5000)) {
            $script:F325SshContainmentFailed = $true
            throw 'SSH output pipes did not close; retain the physical lease'
        }
        return [pscustomobject]@{ExitCode=$process.ExitCode;Stdout=$stdoutTask.GetAwaiter().GetResult();Stderr=$stderrTask.GetAwaiter().GetResult()}
    } finally {
        try { Stop-F325SshProcess -Process $process -Started $didStart }
        finally { $process.Dispose() }
    }
}
