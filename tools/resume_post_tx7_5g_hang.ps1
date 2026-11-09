param(
    [string]$HostAddress = "192.168.1.90",
    [int]$RecoveryTimeout = 20,
    [switch]$ExecuteRecovery,
    [switch]$VerifyLyokoReentry,
    [string]$Ack,
    [string]$OutputDir
)

$ErrorActionPreference = "Stop"
$ResumeAck = "OPENMITRASTAR_RESUME_AFTER_TX7_HANG_READONLY"
$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$StateFile = Join-Path $Root "work\mission-state\HARDWARE_STATE.json"
$RecoveryGate = Join-Path $PSScriptRoot "verify_post_tx7_recovery.ps1"
$LyokoReentryGate = Join-Path $PSScriptRoot "verify_router_lyoko_reentry.ps1"
$Tx11BootCollector = Join-Path $PSScriptRoot "collect_w2_tx11_boot_evidence.ps1"
$Tx11Gate = Join-Path $PSScriptRoot "run_w2_2g_tx11_gate.ps1"
$ResumeResultVerifier = Join-Path $PSScriptRoot "verify_resume_post_tx7_result.py"
$PowerShellExe = "powershell"
$Python = "python"

foreach ($Required in @($StateFile, $RecoveryGate, $LyokoReentryGate, $Tx11BootCollector, $Tx11Gate, $ResumeResultVerifier)) {
    if (-not (Test-Path -LiteralPath $Required -PathType Leaf)) {
        throw "Missing required file: $Required"
    }
}

$State = Get-Content -LiteralPath $StateFile -Raw | ConvertFrom-Json
$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
if ([string]::IsNullOrWhiteSpace($OutputDir)) {
    $OutputDir = Join-Path $Root "outputs\recovery\resume-post-tx7-$Stamp-READONLY"
}
$OutputDir = [IO.Path]::GetFullPath($OutputDir)
$AllowedRoot = [IO.Path]::GetFullPath((Join-Path $Root "outputs\recovery"))
$AllowedPrefix = $AllowedRoot.TrimEnd([IO.Path]::DirectorySeparatorChar, [IO.Path]::AltDirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
if (($OutputDir -ne $AllowedRoot) -and
    (-not $OutputDir.StartsWith($AllowedPrefix, [StringComparison]::OrdinalIgnoreCase))) {
    throw "OutputDir must stay under $AllowedRoot"
}

$Plan = [ordered]@{
    schema = "openmitrastar.resume-post-tx7-5g-hang/v1"
    mode = if ($ExecuteRecovery) { "execute-recovery-readonly" } else { "plan-only" }
    ack_required = $ResumeAck
    host = $HostAddress
    output_dir = $OutputDir
    current_state = [ordered]@{
        boot_state = $State.current_observation.boot_state
        current_access = $State.current_observation.current_access
        latest_ready_image_sha256 = $State.current_observation.latest_ready_image_sha256
    }
    ordered_flow = @(
        "physical power-cycle outside this script",
        "post-power-cycle recovery proof through verify_post_tx7_recovery.ps1",
        "optional Router-Lyoko live reentry proof through verify_router_lyoko_reentry.ps1",
        "if recovery passes, print the TX11 boot-evidence collection plan and TX11 2.4 GHz client gate plan",
        "preserve recovery-result.json for the later ACK-gated TX11 exact RAM boot and client execution gate",
        "operator connects one client to OpenMitraStar-2G-DIAG before running the long monitor"
    )
    recovery_gate = $RecoveryGate
    lyoko_reentry_gate = $LyokoReentryGate
    resume_result_verifier = $ResumeResultVerifier
    lyoko_reentry_required_for_resume = [bool]$VerifyLyokoReentry
    next_boot_evidence_gate = $Tx11BootCollector
    next_2g_gate = $Tx11Gate
    mutations = [ordered]@{
        uart_opened = $false
        module_reload = $false
        network_reconfigure = $false
        bootenv = $false
        mtd = $false
        flash = $false
    }
}

if (-not $ExecuteRecovery) {
    $Plan | ConvertTo-Json -Depth 6
    Write-Output "OMPOSTTX7_RESUME_PLAN_PASS=1"
    exit 0
}

if ($Ack -ne $ResumeAck) {
    throw "Execution requires -Ack $ResumeAck"
}

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$RecoveryOutputDir = Join-Path $OutputDir "post-tx7-recovery"
$LyokoOutputDir = Join-Path $OutputDir "router-lyoko-reentry"
$RecoveryStdout = Join-Path $OutputDir "recovery.stdout.txt"
$RecoveryStderr = Join-Path $OutputDir "recovery.stderr.txt"
$RecoveryResultJson = Join-Path $RecoveryOutputDir "recovery-result.json"
$LyokoStdout = Join-Path $OutputDir "lyoko-reentry.stdout.txt"
$LyokoStderr = Join-Path $OutputDir "lyoko-reentry.stderr.txt"
$LyokoResultJson = Join-Path $LyokoOutputDir "lyoko-reentry-result.json"
$Tx11BootPlanStdout = Join-Path $OutputDir "tx11-boot-evidence-plan.stdout.txt"
$Tx11BootPlanStderr = Join-Path $OutputDir "tx11-boot-evidence-plan.stderr.txt"
$Tx11PlanStdout = Join-Path $OutputDir "tx11-2g-plan.stdout.txt"
$Tx11PlanStderr = Join-Path $OutputDir "tx11-2g-plan.stderr.txt"
$ResumeResultJson = Join-Path $OutputDir "resume-result.json"
$ResumeResultVerifierOut = Join-Path $OutputDir "resume-result-verifier.stdout.json"
$ResumeResultVerifierErr = Join-Path $OutputDir "resume-result-verifier.stderr.txt"

Write-Output "OMPOSTTX7_RESUME_RECOVERY_START host=$HostAddress"
& $PowerShellExe -NoProfile -ExecutionPolicy Bypass -File $RecoveryGate `
    -HostAddress $HostAddress `
    -Timeout $RecoveryTimeout `
    -Execute `
    -Ack "OPENMITRASTAR_POST_TX7_RECOVERY_READONLY" `
    -OutputDir $RecoveryOutputDir > $RecoveryStdout 2> $RecoveryStderr
$RecoveryExit = $LASTEXITCODE

$RecoveryPass = $false
try {
    $RecoveryResult = Get-Content -LiteralPath $RecoveryResultJson -Raw | ConvertFrom-Json
    $RecoveryPass = [bool]$RecoveryResult.pass -and [bool]$RecoveryResult.result_verifier_ok
} catch {
    $RecoveryPass = $false
}

$LyokoExit = -1
$LyokoPass = $false
if ($VerifyLyokoReentry) {
    Write-Output "OMPOSTTX7_RESUME_LYOKO_REENTRY_START host=$HostAddress"
    & $PowerShellExe -NoProfile -ExecutionPolicy Bypass -File $LyokoReentryGate `
        -HostAddress $HostAddress `
        -Timeout $RecoveryTimeout `
        -Execute `
        -Ack "OPENMITRASTAR_LYOKO_REENTRY_READONLY" `
        -OutputDir $LyokoOutputDir > $LyokoStdout 2> $LyokoStderr
    $LyokoExit = $LASTEXITCODE
    try {
        $LyokoResult = Get-Content -LiteralPath $LyokoResultJson -Raw | ConvertFrom-Json
        $LyokoPass = [bool]$LyokoResult.pass -and [bool]$LyokoResult.result_verifier_ok
    } catch {
        $LyokoPass = $false
    }
}

$Tx11BootPlanReady = $false
& $PowerShellExe -NoProfile -ExecutionPolicy Bypass -File $Tx11BootCollector -HostAddress $HostAddress > $Tx11BootPlanStdout 2> $Tx11BootPlanStderr
$Tx11BootPlanExit = $LASTEXITCODE
if (Test-Path -LiteralPath $Tx11BootPlanStdout -PathType Leaf) {
    $Tx11BootPlanText = Get-Content -LiteralPath $Tx11BootPlanStdout -Raw
    $Tx11BootPlanReady = $Tx11BootPlanText -match "OMTX11_BOOT_EVIDENCE_COLLECTION_PLAN_PASS=1"
}

$Tx11PlanReady = $false
& $PowerShellExe -NoProfile -ExecutionPolicy Bypass -File $Tx11Gate -HostAddress $HostAddress > $Tx11PlanStdout 2> $Tx11PlanStderr
$Tx11PlanExit = $LASTEXITCODE
if (Test-Path -LiteralPath $Tx11PlanStdout -PathType Leaf) {
    $Tx11PlanText = Get-Content -LiteralPath $Tx11PlanStdout -Raw
    $Tx11PlanReady = $Tx11PlanText -match "OM2G_TX11_GATE_PLAN_PASS=1"
}

$Pass = (
    ($RecoveryExit -eq 0) -and
    $RecoveryPass -and
    ($Tx11BootPlanExit -eq 0) -and
    $Tx11BootPlanReady -and
    ($Tx11PlanExit -eq 0) -and
    $Tx11PlanReady -and
    ((-not $VerifyLyokoReentry) -or (($LyokoExit -eq 0) -and $LyokoPass))
)

$Result = [ordered]@{
    schema = "openmitrastar.resume-post-tx7-5g-hang-result/v1"
    status = if ($Pass) { "RESUME_POST_TX7_READY_FOR_2G_CLIENT_GATE" } else { "RESUME_POST_TX7_NOT_READY" }
    pass = [bool]$Pass
    host = $HostAddress
    recovery_exit = $RecoveryExit
    recovery_pass = [bool]$RecoveryPass
    lyoko_reentry_required = [bool]$VerifyLyokoReentry
    lyoko_reentry_exit = $LyokoExit
    lyoko_reentry_pass = [bool]$LyokoPass
    tx11_boot_plan_exit = $Tx11BootPlanExit
    tx11_boot_plan_ready = [bool]$Tx11BootPlanReady
    tx11_2g_plan_exit = $Tx11PlanExit
    tx11_2g_plan_ready = [bool]$Tx11PlanReady
    evidence = [ordered]@{
        output_dir = $OutputDir
        recovery_stdout = $RecoveryStdout
        recovery_stderr = $RecoveryStderr
        recovery_result_json = $RecoveryResultJson
        lyoko_stdout = if ($VerifyLyokoReentry) { $LyokoStdout } else { "" }
        lyoko_stderr = if ($VerifyLyokoReentry) { $LyokoStderr } else { "" }
        lyoko_result_json = if ($VerifyLyokoReentry) { $LyokoResultJson } else { "" }
        tx11_boot_plan_stdout = $Tx11BootPlanStdout
        tx11_boot_plan_stderr = $Tx11BootPlanStderr
        tx11_2g_plan_stdout = $Tx11PlanStdout
        tx11_2g_plan_stderr = $Tx11PlanStderr
        result_verifier_stdout = $ResumeResultVerifierOut
        result_verifier_stderr = $ResumeResultVerifierErr
        result_json = $ResumeResultJson
    }
    mutations = [ordered]@{
        uart_opened = $false
        module_reload = $false
        network_reconfigure = $false
        bootenv = $false
        mtd = $false
        flash = $false
    }
}

$Result | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $ResumeResultJson -Encoding UTF8
$ResultVerifierExit = 1
try {
    & $Python $ResumeResultVerifier `
        $ResumeResultJson `
        --output-dir $OutputDir > $ResumeResultVerifierOut 2> $ResumeResultVerifierErr
    $ResultVerifierExit = $LASTEXITCODE
} catch {
    $_ | Out-String | Set-Content -LiteralPath $ResumeResultVerifierErr -Encoding UTF8
    $ResultVerifierExit = 1
}
$ResultVerifierOk = $false
$ResultVerifierStatus = "RESUME_RESULT_UNPARSEABLE"
try {
    $ResultVerifierStdout = Get-Content -LiteralPath $ResumeResultVerifierOut -Raw
    $ResultVerifierReport = $ResultVerifierStdout | ConvertFrom-Json
    $ResultVerifierOk = [bool]$ResultVerifierReport.ok
    $ResultVerifierStatus = if ($ResultVerifierOk) { "RESUME_RESULT_VERIFIED_READONLY" } else { "RESUME_RESULT_NOT_VERIFIED" }
} catch {
    $ResultVerifierOk = $false
}
$Result["result_verifier_exit"] = $ResultVerifierExit
$Result["result_verifier_ok"] = [bool]$ResultVerifierOk
$Result["result_verifier_status"] = $ResultVerifierStatus
$Result | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $ResumeResultJson -Encoding UTF8
$Result | ConvertTo-Json -Depth 6

$FinalPass = $Pass -and ($ResultVerifierExit -eq 0) -and $ResultVerifierOk
if ($FinalPass) {
    Write-Output "OMPOSTTX7_RESUME_PASS=1 next=collect_w2_tx11_boot_evidence_then_run_w2_tx11_gate recovery_result_json=$RecoveryResultJson evidence=$OutputDir"
    exit 0
}

if ($RecoveryExit -ne 0 -or (-not $RecoveryPass)) {
    Write-Output "OMPOSTTX7_RESUME_STOP recovery_rc=$RecoveryExit evidence=$OutputDir"
    exit $(if ($RecoveryExit -ne 0) { $RecoveryExit } else { 2 })
}
if ($VerifyLyokoReentry -and (($LyokoExit -ne 0) -or (-not $LyokoPass))) {
    Write-Output "OMPOSTTX7_RESUME_STOP lyoko_reentry_rc=$LyokoExit evidence=$OutputDir"
    exit $(if ($LyokoExit -ne 0) { $LyokoExit } else { 2 })
}
if ($Tx11BootPlanExit -ne 0 -or (-not $Tx11BootPlanReady)) {
    Write-Output "OMPOSTTX7_RESUME_STOP tx11_boot_plan_rc=$Tx11BootPlanExit evidence=$OutputDir"
    exit $(if ($Tx11BootPlanExit -ne 0) { $Tx11BootPlanExit } else { 2 })
}
if ($Tx11PlanExit -ne 0 -or (-not $Tx11PlanReady)) {
    Write-Output "OMPOSTTX7_RESUME_STOP tx11_2g_plan_rc=$Tx11PlanExit evidence=$OutputDir"
    exit $(if ($Tx11PlanExit -ne 0) { $Tx11PlanExit } else { 2 })
}
Write-Output "OMPOSTTX7_RESUME_PASS=0 evidence=$OutputDir"
exit 2
