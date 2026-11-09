param(
    [string]$Target = "192.168.1.46:26101"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Sdb = Join-Path $Root "tools\tizen-sdb\data\tools\sdb.exe"
$Exec = Join-Path $Root "tools\samsung_sdb_exec.py"
$Lib = Join-Path $Root "outputs\samsung-m5\libdotnet_inhouse_inject_libc.so"

& $Sdb kill-server | Out-Host
Start-Sleep -Seconds 1
& $Sdb connect $Target | Out-Host
& $Sdb devices | Out-Host

& $Sdb -s $Target push $Lib /home/owner/share/tmp/sdk_tools/heaptrack/libinhouse_libc.so | Out-Host

$prep = "mkdir -p /opt/usr/apps/appdrm/codex; cp /home/owner/share/tmp/sdk_tools/heaptrack/libinhouse_libc.so /opt/usr/apps/appdrm/codex/libinject.so; rm -f /home/owner/share/tmp/dotnet-inhouse-probe.txt; ls -lZ /opt/usr/apps/appdrm/codex/libinject.so; echo __END__"
python $Exec $prep --timeout 25 | Out-Host

$run1 = "DOTNET_LAUNCHER_INJECT=/opt/usr/apps/appdrm/codex/libinject.so /usr/bin/dotnet-launcher-inhouse; echo ran1; cat /home/owner/share/tmp/dotnet-inhouse-probe.txt 2>/dev/null; echo __END__"
python $Exec $run1 --timeout 25 | Out-Host

$run2 = "rm -f /home/owner/share/tmp/dotnet-inhouse-probe.txt /home/owner/share/tmp/inhouse-run.txt; DOTNET_LAUNCHER_INJECT=/opt/usr/apps/appdrm/codex/libinject.so /usr/bin/dotnet-launcher-inhouse --standalone /usr/apps/com.samsung.tv.dotnet-policy-checker/bin/DotnetPolicyChecker.dll >/home/owner/share/tmp/inhouse-run.txt 2>&1; echo ran2; cat /home/owner/share/tmp/dotnet-inhouse-probe.txt 2>/dev/null; echo RUN; cat /home/owner/share/tmp/inhouse-run.txt 2>/dev/null; echo __END__"
python $Exec $run2 --timeout 35 | Out-Host

$logs = "dlogutil -d DOTNET_LAUNCHER:I '*:S' 2>/dev/null | tail -120; echo __END__"
python $Exec $logs --timeout 20 | Out-Host
