param([switch]$Execute,[string]$Ack="",[string]$Port="COM3",[string]$HostIp="192.168.1.200",[string]$ServerIp="192.168.1.43",[int]$TimeoutSeconds=480)
$ErrorActionPreference="Stop"
$RequiredAck="OPENMITRASTAR_QTN_W3_CONGEST_ONLY"
$Root=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$ImageName="linux510-product-watchdog-canary-v1-RAM-ONLY.bin"
$Image=Join-Path $Root "work\tftp\omvl\$ImageName"
$ImageSha="5e6dd1b4a7f19e29219287f5a53b9be37722666690f019cfd75daef3e9d96358"
$Artifact=Join-Path $Root "outputs\kernel-port\quantenna-linux510-v89-radiohw-congest-routed-20260818-2130"
$Manifest=Join-Path $Root "work\mission-state\w3-offline\W3_V89_RADIOHW_CONGEST_SIGNED_ARTIFACT.json"
$ClosedGate=Join-Path $Root "work\mission-state\w3-offline\W3_CONGEST_ONLY_GATE.env"
$ApprovedGate=Join-Path $Root "work\mission-state\w3-offline\W3_CONGEST_ONLY_GATE.approved.env"
$Gate=if($Execute){$ApprovedGate}else{$ClosedGate}
$RemoteScript=Join-Path $PSScriptRoot "qtn_w3_congest_only_remote.sh"
$Release="5.10.260-openmitrastar-radiohw"
if((Get-FileHash -Algorithm SHA256 -LiteralPath $Image).Hash.ToLowerInvariant() -ne $ImageSha){throw "watchdog image hash mismatch"}
& python.exe (Join-Path $PSScriptRoot "qtn_w3_artifact_gate.py") --manifest $Manifest --verify
if($LASTEXITCODE){throw "signed congest artifact verification failed"}
$g=@{}; Get-Content $Gate|%{if($_ -match '^([^#=]+)=(.*)$'){$g[$matches[1]]=$matches[2]}}
[ordered]@{mode=if($Execute){"EXECUTE_CONGEST_ONLY"}else{"DRY_RUN"}; pair=$g.W3_PAIR_APPROVED; hbm_proven=$g.W3_HBM_ONLY_PROVEN; approved=$g.W3_CONGEST_ONLY_APPROVED; gate_sha256=(Get-FileHash -Algorithm SHA256 -LiteralPath $Gate).Hash.ToLowerInvariant(); broader_hardware=$g.W3_HARDWARE_ACTIVE_APPROVED; dependencies=@("qtn_platform_support","hbm"); added_variable="topaz_congest_queue.ko"; switch_tqe="forbidden"; recovery="watchdog+UART+ordered unload"}|ConvertTo-Json -Depth 4
if(-not $Execute){"W3_CONGEST_ONLY_DRY_RUN_PASS=1";exit 0}
if($Ack -cne $RequiredAck){throw "execution requires -Ack $RequiredAck"}
if($g.W3_CONGEST_ONLY_APPROVED -ne "1" -or $g.W3_HBM_ONLY_PROVEN -ne "1" -or $g.W3_HARDWARE_ACTIVE_APPROVED -ne "0"){throw "congest gate conditions not met"}
$tftp=$null;$capture=$null
try{
 $tftp=Start-Process python.exe -WindowStyle Hidden -PassThru -ArgumentList @((Join-Path $PSScriptRoot "tftp_serve_once.py"),"--root",(Split-Path $Image),"--bind","0.0.0.0","--port","69","--timeout","$TimeoutSeconds","--once");Start-Sleep -Milliseconds 600
 & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "reboot_boot_ramssh.ps1") -Port $Port -Filename $ImageName -ServerIp $ServerIp -ClientIp $HostIp -TimeoutSeconds $TimeoutSeconds -EntropyPromptPattern '(?s)OMPRODUCT_ENTR.{0,4096}OPY_SEED_REQUIRED' -EntropyOkPattern 'OMPRODUCT_SERIAL_ENTROPY_OK bits=256' -ReadyPattern 'OMPRODUCT_READY state=(ready|degraded)';if($LASTEXITCODE){throw "RAM boot failed"}
 & python.exe (Join-Path $PSScriptRoot "ramssh_exec.py") "dmesg | grep -E 'OMWDT stage=(armed|pet first=1)'" --host $HostIp;if($LASTEXITCODE){throw "watchdog markers absent"}
 $uartDir=Join-Path $Root ("outputs\uart-live\w3-congest-only-"+(Get-Date -Format "yyyyMMdd-HHmmss"));$capture=Start-Process powershell.exe -WindowStyle Hidden -PassThru -ArgumentList @("-NoProfile","-ExecutionPolicy","Bypass","-File",(Join-Path $PSScriptRoot "capture_topaz_uart.ps1"),"-Port",$Port,"-Seconds","180","-OutputDirectory",$uartDir)
 & python.exe (Join-Path $PSScriptRoot "ramssh_exec.py") "rm -rf /tmp/w3-qtn-congest; mkdir -p /tmp/w3-qtn-congest" --host $HostIp
 $mods=@("platform/ruby/qtn_pm_qos_compat.ko","platform/ruby/board_compat.ko","platform/ruby/runtime_compat.ko","platform/ruby/qtn_platform_support.ko","platform/ruby/iputil.ko","platform/ruby/dmautil.ko","platform/topaz/switch_vlan.ko","platform/topaz/fwt_if.ko","platform/topaz/hbm.ko","platform/topaz/topaz_congest_queue.ko")
 foreach($rel in $mods){$src=Join-Path $Artifact ("rootfs\lib\modules\$Release\extra\quantenna\"+($rel -replace '/', '\'));$dst="/tmp/w3-qtn-congest/"+[IO.Path]::GetFileName($src);& python.exe (Join-Path $PSScriptRoot "ramssh_upload.py") $src $dst --host $HostIp --mode 0600;if($LASTEXITCODE){throw "upload failed $rel"}}
 & python.exe (Join-Path $PSScriptRoot "ramssh_upload.py") $Gate /tmp/W3_CONGEST_ONLY_GATE.env --host $HostIp --mode 0600
 & python.exe (Join-Path $PSScriptRoot "ramssh_upload.py") $RemoteScript /tmp/qtn_w3_congest_only_remote.sh --host $HostIp --mode 0700
 & python.exe (Join-Path $PSScriptRoot "ramssh_exec.py") "sed -i 's/\r$//' /tmp/W3_CONGEST_ONLY_GATE.env /tmp/qtn_w3_congest_only_remote.sh; sh /tmp/qtn_w3_congest_only_remote.sh /tmp/w3-qtn-congest /tmp/W3_CONGEST_ONLY_GATE.env" --host $HostIp --timeout 120;if($LASTEXITCODE){throw "congest-only remote failed"}
}catch{if($capture -and -not $capture.HasExited){Stop-Process -Id $capture.Id -Force -ErrorAction SilentlyContinue};& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "uart_sysrq_reboot.ps1") -Port $Port;throw}finally{if($capture -and -not $capture.HasExited){Stop-Process -Id $capture.Id -Force -ErrorAction SilentlyContinue};if($tftp -and -not $tftp.HasExited){Stop-Process -Id $tftp.Id -Force -ErrorAction SilentlyContinue}}
"W3_CONGEST_ONLY_EXPERIMENT_PASS=1"
