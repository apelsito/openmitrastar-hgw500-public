param(
    [string]$HostAddress = "192.168.1.90",
    [int]$Timeout = 5,
    [switch]$Execute,
    [string]$Ack,
    [string]$OutputDir
)

$ErrorActionPreference = "Stop"
$AckRequired = "OPENMITRASTAR_LYOKO_REENTRY_READONLY"
$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$LiveVerifier = Join-Path $PSScriptRoot "verify_router_lyoko_live.py"
$ControlVerifier = Join-Path $PSScriptRoot "verify_router_lyoko_control_api.py"
$StaticIndexVerifier = Join-Path $PSScriptRoot "verify_router_lyoko_static_index.py"
$ServedFilesVerifier = Join-Path $PSScriptRoot "verify_router_lyoko_served_files.py"
$ServedNoSecretsVerifier = Join-Path $PSScriptRoot "verify_router_lyoko_served_no_secrets.py"
$ResultVerifier = Join-Path $PSScriptRoot "verify_router_lyoko_reentry_result.py"
$OverlayManifest = Join-Path $Root "work\mission-state\router-lyoko-v0\manifest.json"
$Python = "python"

foreach ($Required in @($LiveVerifier, $ControlVerifier, $StaticIndexVerifier, $ServedFilesVerifier, $ServedNoSecretsVerifier, $ResultVerifier, $OverlayManifest)) {
    if (-not (Test-Path -LiteralPath $Required -PathType Leaf)) {
        throw "Missing required file: $Required"
    }
}

$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
if ([string]::IsNullOrWhiteSpace($OutputDir)) {
    $OutputDir = Join-Path $Root "outputs\recovery\router-lyoko-reentry-$Stamp-READONLY"
}
$OutputDir = [IO.Path]::GetFullPath($OutputDir)
$AllowedRoot = [IO.Path]::GetFullPath((Join-Path $Root "outputs\recovery"))
$AllowedPrefix = $AllowedRoot.TrimEnd([IO.Path]::DirectorySeparatorChar, [IO.Path]::AltDirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
if (($OutputDir -ne $AllowedRoot) -and
    (-not $OutputDir.StartsWith($AllowedPrefix, [StringComparison]::OrdinalIgnoreCase))) {
    throw "OutputDir must stay under $AllowedRoot"
}

$StateUrl = "http://$HostAddress/api/lyoko"
$ControlUrl = "http://$HostAddress/api/lyoko-control"
$StaticIndexUrl = "http://$HostAddress/lyoko-data/index.json"
$Plan = [ordered]@{
    schema = "router-lyoko.reentry-live-api-gate/v1"
    mode = if ($Execute) { "execute-readonly" } else { "plan-only" }
    host = $HostAddress
    state_url = $StateUrl
    control_url = $ControlUrl
    static_index_url = $StaticIndexUrl
    overlay_manifest = $OverlayManifest
    ack_required = $AckRequired
    output_dir = $OutputDir
    operations = @(
        "GET /api/lyoko from the recovered router",
        "validate the response with tools/verify_router_lyoko_live.py",
        "require kernel 5.10, bridge up, SSH tower running, runtime_bridge management path proven and runtime_recovery guards proven",
        "GET /api/lyoko-control from the recovered router",
        "validate the fail-closed observe-only control contract with tools/verify_router_lyoko_control_api.py",
        "GET /lyoko-data/index.json from the recovered router",
        "validate static lyoko-data bytes/SHA256 against the local overlay manifest with tools/verify_router_lyoko_static_index.py",
        "GET /lyoko.html, /lyoko.css, /lyoko.js and /lyoko-data/* from the recovered router",
        "validate served web/static bytes/SHA256 against the local overlay manifest with tools/verify_router_lyoko_served_files.py",
        "validate served /api/lyoko, /api/lyoko-control and web/static payloads expose no concrete secrets with tools/verify_router_lyoko_served_no_secrets.py",
        "validate lyoko-reentry-result.json against verifier stdout/exits/classifications/path confinement with tools/verify_router_lyoko_reentry_result.py",
        "write local verifier stdout/stderr/result JSON under outputs/recovery"
    )
    mutations = [ordered]@{
        uart_opened = $false
        ssh_command = $false
        reboot = $false
        network_reconfigure = $false
        bootenv = $false
        mtd = $false
        flash = $false
    }
}

if (-not $Execute) {
    $Plan | ConvertTo-Json -Depth 6
    Write-Output "OMLYOKO_REENTRY_PLAN_PASS=1"
    exit 0
}

if ($Ack -ne $AckRequired) {
    throw "Execution requires -Ack $AckRequired"
}

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$VerifierOut = Join-Path $OutputDir "lyoko-live-verifier.stdout.json"
$VerifierErr = Join-Path $OutputDir "lyoko-live-verifier.stderr.txt"
$ControlVerifierOut = Join-Path $OutputDir "lyoko-control-verifier.stdout.json"
$ControlVerifierErr = Join-Path $OutputDir "lyoko-control-verifier.stderr.txt"
$StaticIndexVerifierOut = Join-Path $OutputDir "lyoko-static-index-verifier.stdout.json"
$StaticIndexVerifierErr = Join-Path $OutputDir "lyoko-static-index-verifier.stderr.txt"
$ServedFilesVerifierOut = Join-Path $OutputDir "lyoko-served-files-verifier.stdout.json"
$ServedFilesVerifierErr = Join-Path $OutputDir "lyoko-served-files-verifier.stderr.txt"
$ServedNoSecretsVerifierOut = Join-Path $OutputDir "lyoko-served-no-secrets-verifier.stdout.json"
$ServedNoSecretsVerifierErr = Join-Path $OutputDir "lyoko-served-no-secrets-verifier.stderr.txt"
$ResultVerifierOut = Join-Path $OutputDir "lyoko-reentry-result-verifier.stdout.json"
$ResultVerifierErr = Join-Path $OutputDir "lyoko-reentry-result-verifier.stderr.txt"
$ResultJson = Join-Path $OutputDir "lyoko-reentry-result.json"

$VerifierExit = 1
try {
    & $Python $LiveVerifier `
        --url $StateUrl `
        --timeout $Timeout `
        --require-kernel-510 `
        --require-bridge-up `
        --require-ssh-running `
        --require-management-path `
        --require-recovery-guards > $VerifierOut 2> $VerifierErr
    $VerifierExit = $LASTEXITCODE
} catch {
    $_ | Out-String | Set-Content -LiteralPath $VerifierErr -Encoding UTF8
    $VerifierExit = 1
}

$ControlVerifierExit = 1
try {
    & $Python $ControlVerifier `
        --url $ControlUrl `
        --timeout $Timeout > $ControlVerifierOut 2> $ControlVerifierErr
    $ControlVerifierExit = $LASTEXITCODE
} catch {
    $_ | Out-String | Set-Content -LiteralPath $ControlVerifierErr -Encoding UTF8
    $ControlVerifierExit = 1
}

$StaticIndexVerifierExit = 1
try {
    & $Python $StaticIndexVerifier `
        --url $StaticIndexUrl `
        --manifest $OverlayManifest `
        --timeout $Timeout > $StaticIndexVerifierOut 2> $StaticIndexVerifierErr
    $StaticIndexVerifierExit = $LASTEXITCODE
} catch {
    $_ | Out-String | Set-Content -LiteralPath $StaticIndexVerifierErr -Encoding UTF8
    $StaticIndexVerifierExit = 1
}

$ServedFilesVerifierExit = 1
try {
    & $Python $ServedFilesVerifier `
        --base-url "http://$HostAddress" `
        --manifest $OverlayManifest `
        --timeout $Timeout > $ServedFilesVerifierOut 2> $ServedFilesVerifierErr
    $ServedFilesVerifierExit = $LASTEXITCODE
} catch {
    $_ | Out-String | Set-Content -LiteralPath $ServedFilesVerifierErr -Encoding UTF8
    $ServedFilesVerifierExit = 1
}

$ServedNoSecretsVerifierExit = 1
try {
    & $Python $ServedNoSecretsVerifier `
        --base-url "http://$HostAddress" `
        --manifest $OverlayManifest `
        --timeout $Timeout > $ServedNoSecretsVerifierOut 2> $ServedNoSecretsVerifierErr
    $ServedNoSecretsVerifierExit = $LASTEXITCODE
} catch {
    $_ | Out-String | Set-Content -LiteralPath $ServedNoSecretsVerifierErr -Encoding UTF8
    $ServedNoSecretsVerifierExit = 1
}

$VerifierStdout = ""
if (Test-Path -LiteralPath $VerifierOut -PathType Leaf) {
    $VerifierStdout = Get-Content -LiteralPath $VerifierOut -Raw
}
$VerifierStderr = ""
if (Test-Path -LiteralPath $VerifierErr -PathType Leaf) {
    $VerifierStderr = Get-Content -LiteralPath $VerifierErr -Raw
}

$ControlVerifierStdout = ""
if (Test-Path -LiteralPath $ControlVerifierOut -PathType Leaf) {
    $ControlVerifierStdout = Get-Content -LiteralPath $ControlVerifierOut -Raw
}
$ControlVerifierStderr = ""
if (Test-Path -LiteralPath $ControlVerifierErr -PathType Leaf) {
    $ControlVerifierStderr = Get-Content -LiteralPath $ControlVerifierErr -Raw
}

$StaticIndexVerifierStdout = ""
if (Test-Path -LiteralPath $StaticIndexVerifierOut -PathType Leaf) {
    $StaticIndexVerifierStdout = Get-Content -LiteralPath $StaticIndexVerifierOut -Raw
}
$StaticIndexVerifierStderr = ""
if (Test-Path -LiteralPath $StaticIndexVerifierErr -PathType Leaf) {
    $StaticIndexVerifierStderr = Get-Content -LiteralPath $StaticIndexVerifierErr -Raw
}

$ServedFilesVerifierStdout = ""
if (Test-Path -LiteralPath $ServedFilesVerifierOut -PathType Leaf) {
    $ServedFilesVerifierStdout = Get-Content -LiteralPath $ServedFilesVerifierOut -Raw
}
$ServedFilesVerifierStderr = ""
if (Test-Path -LiteralPath $ServedFilesVerifierErr -PathType Leaf) {
    $ServedFilesVerifierStderr = Get-Content -LiteralPath $ServedFilesVerifierErr -Raw
}

$ServedNoSecretsVerifierStdout = ""
if (Test-Path -LiteralPath $ServedNoSecretsVerifierOut -PathType Leaf) {
    $ServedNoSecretsVerifierStdout = Get-Content -LiteralPath $ServedNoSecretsVerifierOut -Raw
}
$ServedNoSecretsVerifierStderr = ""
if (Test-Path -LiteralPath $ServedNoSecretsVerifierErr -PathType Leaf) {
    $ServedNoSecretsVerifierStderr = Get-Content -LiteralPath $ServedNoSecretsVerifierErr -Raw
}

$VerifierOk = $false
$StateVerifierStatus = "STATE_UNPARSEABLE"
try {
    $VerifierReport = $VerifierStdout | ConvertFrom-Json
    $VerifierOk = [bool]$VerifierReport.ok
    $StateVerifierStatus = if ($VerifierOk) { "LYOKO_STATE_PROVEN_READONLY" } else { "LYOKO_STATE_NOT_PROVEN" }
} catch {
    $VerifierOk = $false
}

$ControlVerifierOk = $false
$ControlVerifierStatus = "CONTROL_UNPARSEABLE"
try {
    $ControlVerifierReport = $ControlVerifierStdout | ConvertFrom-Json
    $ControlVerifierOk = [bool]$ControlVerifierReport.ok
    $ControlVerifierStatus = if ($ControlVerifierOk) { "LYOKO_CONTROL_PROVEN_READONLY" } else { "LYOKO_CONTROL_NOT_PROVEN" }
} catch {
    $ControlVerifierOk = $false
}

$StaticIndexVerifierOk = $false
$StaticIndexVerifierStatus = "STATIC_INDEX_UNPARSEABLE"
try {
    $StaticIndexVerifierReport = $StaticIndexVerifierStdout | ConvertFrom-Json
    $StaticIndexVerifierOk = [bool]$StaticIndexVerifierReport.ok
    $StaticIndexVerifierStatus = if ($StaticIndexVerifierOk) { "LYOKO_STATIC_INDEX_PROVEN_READONLY" } else { "LYOKO_STATIC_INDEX_NOT_PROVEN" }
} catch {
    $StaticIndexVerifierOk = $false
}

$ServedFilesVerifierOk = $false
$ServedFilesVerifierStatus = "SERVED_FILES_UNPARSEABLE"
try {
    $ServedFilesVerifierReport = $ServedFilesVerifierStdout | ConvertFrom-Json
    $ServedFilesVerifierOk = [bool]$ServedFilesVerifierReport.ok
    $ServedFilesVerifierStatus = if ($ServedFilesVerifierOk) { "LYOKO_SERVED_FILES_PROVEN_READONLY" } else { "LYOKO_SERVED_FILES_NOT_PROVEN" }
} catch {
    $ServedFilesVerifierOk = $false
}

$ServedNoSecretsVerifierOk = $false
$ServedNoSecretsVerifierStatus = "SERVED_NO_SECRETS_UNPARSEABLE"
try {
    $ServedNoSecretsVerifierReport = $ServedNoSecretsVerifierStdout | ConvertFrom-Json
    $ServedNoSecretsVerifierOk = [bool]$ServedNoSecretsVerifierReport.ok
    $ServedNoSecretsVerifierStatus = if ($ServedNoSecretsVerifierOk) { "LYOKO_SERVED_NO_SECRETS_PROVEN_READONLY" } else { "LYOKO_SERVED_NO_SECRETS_NOT_PROVEN" }
} catch {
    $ServedNoSecretsVerifierOk = $false
}

$Pass = (
    ($VerifierExit -eq 0) -and
    $VerifierOk -and
    ($ControlVerifierExit -eq 0) -and
    $ControlVerifierOk -and
    ($StaticIndexVerifierExit -eq 0) -and
    $StaticIndexVerifierOk -and
    ($ServedFilesVerifierExit -eq 0) -and
    $ServedFilesVerifierOk -and
    ($ServedNoSecretsVerifierExit -eq 0) -and
    $ServedNoSecretsVerifierOk
)
$Result = [ordered]@{
    schema = "router-lyoko.reentry-live-api-result/v1"
    status = if ($Pass) { "LYOKO_REENTRY_PROVEN_READONLY" } else { "LYOKO_REENTRY_NOT_PROVEN" }
    pass = [bool]$Pass
    host = $HostAddress
    state_url = $StateUrl
    control_url = $ControlUrl
    static_index_url = $StaticIndexUrl
    served_files_base_url = "http://$HostAddress"
    state_verifier_exit = $VerifierExit
    state_verifier_ok = [bool]$VerifierOk
    state_verifier_status = $StateVerifierStatus
    control_verifier_exit = $ControlVerifierExit
    control_verifier_ok = [bool]$ControlVerifierOk
    control_verifier_status = $ControlVerifierStatus
    static_index_verifier_exit = $StaticIndexVerifierExit
    static_index_verifier_ok = [bool]$StaticIndexVerifierOk
    static_index_verifier_status = $StaticIndexVerifierStatus
    served_files_verifier_exit = $ServedFilesVerifierExit
    served_files_verifier_ok = [bool]$ServedFilesVerifierOk
    served_files_verifier_status = $ServedFilesVerifierStatus
    served_no_secrets_verifier_exit = $ServedNoSecretsVerifierExit
    served_no_secrets_verifier_ok = [bool]$ServedNoSecretsVerifierOk
    served_no_secrets_verifier_status = $ServedNoSecretsVerifierStatus
    evidence = [ordered]@{
        output_dir = $OutputDir
        state_verifier_stdout = $VerifierOut
        state_verifier_stderr = $VerifierErr
        control_verifier_stdout = $ControlVerifierOut
        control_verifier_stderr = $ControlVerifierErr
        static_index_verifier_stdout = $StaticIndexVerifierOut
        static_index_verifier_stderr = $StaticIndexVerifierErr
        served_files_verifier_stdout = $ServedFilesVerifierOut
        served_files_verifier_stderr = $ServedFilesVerifierErr
        served_no_secrets_verifier_stdout = $ServedNoSecretsVerifierOut
        served_no_secrets_verifier_stderr = $ServedNoSecretsVerifierErr
        result_verifier_stdout = $ResultVerifierOut
        result_verifier_stderr = $ResultVerifierErr
        result_json = $ResultJson
    }
    mutations = [ordered]@{
        uart_opened = $false
        ssh_command = $false
        reboot = $false
        network_reconfigure = $false
        bootenv = $false
        mtd = $false
        flash = $false
    }
}

$Result | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $ResultJson -Encoding UTF8
$ResultVerifierExit = 1
try {
    & $Python $ResultVerifier `
        $ResultJson `
        --output-dir $OutputDir > $ResultVerifierOut 2> $ResultVerifierErr
    $ResultVerifierExit = $LASTEXITCODE
} catch {
    $_ | Out-String | Set-Content -LiteralPath $ResultVerifierErr -Encoding UTF8
    $ResultVerifierExit = 1
}

$ResultVerifierOk = $false
$ResultVerifierStatus = "REENTRY_RESULT_UNPARSEABLE"
try {
    $ResultVerifierStdout = Get-Content -LiteralPath $ResultVerifierOut -Raw
    $ResultVerifierReport = $ResultVerifierStdout | ConvertFrom-Json
    $ResultVerifierOk = [bool]$ResultVerifierReport.ok
    $ResultVerifierStatus = if ($ResultVerifierOk) { "LYOKO_REENTRY_RESULT_VERIFIED_READONLY" } else { "LYOKO_REENTRY_RESULT_NOT_VERIFIED" }
} catch {
    $ResultVerifierOk = $false
}

$Result["result_verifier_exit"] = $ResultVerifierExit
$Result["result_verifier_ok"] = [bool]$ResultVerifierOk
$Result["result_verifier_status"] = $ResultVerifierStatus
$Result | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $ResultJson -Encoding UTF8
$Result | ConvertTo-Json -Depth 6
$FinalPass = $Pass -and ($ResultVerifierExit -eq 0) -and $ResultVerifierOk
if ($FinalPass) {
    Write-Output "OMLYOKO_REENTRY_PASS=1 evidence=$OutputDir"
    exit 0
}
Write-Output "OMLYOKO_REENTRY_PASS=0 evidence=$OutputDir"
exit 2
