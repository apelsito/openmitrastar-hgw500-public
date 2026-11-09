param(
    [string]$HostName = "192.168.1.1",
    [string]$OutDir = "/workspace/user-home\Desktop\MitraStar\outputs\router-ssh"
)

$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$outJson = Join-Path $OutDir "router-ssh-owner-login-$stamp.json"

Write-Host ""
Write-Host "Router SSH owner login - no se guardara la password." -ForegroundColor Cyan
Write-Host "Host: $HostName"
Write-Host "Prueba primero el usuario de la UI o admin. Evita brute force." -ForegroundColor Yellow
Write-Host ""

$user = Read-Host "Usuario SSH"
$secure = Read-Host "Password SSH" -AsSecureString

$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try {
    $plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
} finally {
    if ($bstr -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    }
}

$env:ROUTER_SSH_HOST = $HostName
$env:ROUTER_SSH_USER = $user
$env:ROUTER_SSH_PASS = $plain
$env:ROUTER_SSH_OUT = $outJson

$py = @'
import json
import os
import sys
import time

sys.path.insert(0, r"/workspace/user-home\Desktop\MitraStar\work\pydeps")

result = {
    "ok": False,
    "host": os.environ.get("ROUTER_SSH_HOST"),
    "user": os.environ.get("ROUTER_SSH_USER"),
    "time_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "commands": {},
}

try:
    import paramiko
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        os.environ["ROUTER_SSH_HOST"],
        username=os.environ["ROUTER_SSH_USER"],
        password=os.environ["ROUTER_SSH_PASS"],
        timeout=8,
        banner_timeout=8,
        auth_timeout=12,
        look_for_keys=False,
        allow_agent=False,
    )
    result["ok"] = True
    read_only = [
        ("id", "id"),
        ("uname", "uname -a"),
        ("proc_version", "cat /proc/version 2>/dev/null | head -1"),
        ("hostname", "hostname 2>/dev/null"),
        ("interfaces", "ip addr 2>/dev/null || ifconfig -a 2>/dev/null"),
        ("routes", "ip route 2>/dev/null || route -n 2>/dev/null"),
        ("netdev", "cat /proc/net/dev 2>/dev/null"),
        ("processes", "ps 2>/dev/null | head -120"),
        ("wifi_tools", "for x in iw iwconfig wl tcapi qcsapi call_qcsapi; do command -v $x 2>/dev/null && echo $x; done"),
        ("dropbear", "ps 2>/dev/null | grep -i '[d]ropbear'; cat /proc/net/tcp 2>/dev/null | head -40"),
    ]
    for name, cmd in read_only:
        stdin, stdout, stderr = client.exec_command(cmd, timeout=10)
        data = (stdout.read() + stderr.read()).decode("utf-8", "replace")
        result["commands"][name] = data[:12000]
    client.close()
except Exception as exc:
    result["error_type"] = type(exc).__name__
    result["error"] = str(exc)
finally:
    result.pop("password", None)
    out = os.environ["ROUTER_SSH_OUT"]
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(json.dumps({"ok": result["ok"], "out": out, "error_type": result.get("error_type")}, ensure_ascii=False))
'@

try {
    $py | python -
} finally {
    Remove-Item Env:\ROUTER_SSH_PASS -ErrorAction SilentlyContinue
    $plain = $null
}

Write-Host ""
Write-Host "Resultado escrito en:" -ForegroundColor Cyan
Write-Host $outJson
Write-Host ""
Read-Host "Pulsa Enter para cerrar"
