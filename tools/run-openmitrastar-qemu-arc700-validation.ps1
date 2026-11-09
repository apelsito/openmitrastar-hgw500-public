param(
    [int]$TimeoutSeconds = 240,
    [string]$Tag = "manual",
    [string]$Kernel = "/workspace/user-home/Desktop/MitraStar/outputs/kernel-port/linux-5.10.260-qemu-arc700-base80000000-console-validation.vmlinux",
    [string]$Append = "ignore_loglevel"
)

$ErrorActionPreference = "Stop"

$workspace = "/workspace/user-home/Desktop/MitraStar"
$qemu = "/home/user/qemu-arc-legacy-build/qemu-system-arc"
$kernel = $Kernel
$log = "$workspace/outputs/emulation/qemu-$Tag.log"
$serial = "$workspace/outputs/emulation/qemu-$Tag.serial.log"
$tmpWin = Join-Path (Get-Location) "outputs\emulation\run-$Tag.sh"
$tmpWsl = "$workspace/outputs/emulation/run-$Tag.sh"

$cmd = @'
set -u
cd "__WORKSPACE__"
rm -f "__LOG__" "__SERIAL__"
timeout __TIMEOUT__s "__QEMU__" \
  -M arc-sim \
  -cpu arc700,has-mpu=false \
  -m 256M \
  -display none \
  -monitor none \
  -no-reboot \
  -serial stdio \
  -d guest_errors \
  -D "__LOG__" \
  -kernel "__KERNEL__" \
  -append "__APPEND__" \
  > "__SERIAL__" 2>&1
code=$?
echo STATUS=$code
wc -c "__LOG__" "__SERIAL__"
{
  grep -n "Linux version" "__SERIAL__" || true
  grep -n "console \[ttyS0\] enabled" "__SERIAL__" || true
  grep -n "Run /init as init process" "__SERIAL__" || true
  grep -n "OPENMITRASTAR_INIT_OK" "__SERIAL__" || true
  grep -n "unable to open an initial console" "__SERIAL__" || true
  grep -n "Failed to execute" "__SERIAL__" || true
  grep -n "unexpected IRQ trap" "__SERIAL__" || true
  grep -n "Kernel panic" "__SERIAL__" || true
  grep -n "Oops" "__SERIAL__" || true
  grep -n "OMT-IRQ" "__LOG__" || true
  grep -n "OMT-PROBE" "__LOG__" || true
  grep -n "OMT-JMP-BAD" "__LOG__" || true
  grep -n "Invalid access" "__LOG__" || true
  grep -n "CPU state at invalid" "__LOG__" || true
} | head -360
tail -80 "__SERIAL__" || true

if [ "$code" != "0" ] && [ "$code" != "124" ]; then
  echo "VALIDATION_FAIL unexpected qemu exit status: $code" >&2
  exit 20
fi
if [ -s "__LOG__" ]; then
  echo "VALIDATION_FAIL guest_errors log is not empty" >&2
  exit 21
fi
grep -q "Linux version" "__SERIAL__" || { echo "VALIDATION_FAIL missing Linux version" >&2; exit 22; }
grep -q "console \[ttyS0\] enabled" "__SERIAL__" || { echo "VALIDATION_FAIL missing ttyS0 console" >&2; exit 23; }
grep -q "Run /init as init process" "__SERIAL__" || { echo "VALIDATION_FAIL missing /init handoff" >&2; exit 24; }
grep -q "OPENMITRASTAR_INIT_OK" "__SERIAL__" || { echo "VALIDATION_FAIL userspace marker missing" >&2; exit 26; }
if grep -Eq "Kernel panic|Oops|BUG|Unhandled|unable to open an initial console|Failed to execute|unexpected IRQ trap|Invalid access" "__SERIAL__" "__LOG__"; then
  echo "VALIDATION_FAIL failure pattern matched" >&2
  exit 25
fi
echo "VALIDATION_OK"
'@

$cmd = $cmd.Replace("__WORKSPACE__", $workspace).
    Replace("__LOG__", $log).
    Replace("__SERIAL__", $serial).
    Replace("__TIMEOUT__", [string]$TimeoutSeconds).
    Replace("__QEMU__", $qemu).
    Replace("__KERNEL__", $kernel).
    Replace("__APPEND__", $Append)

Set-Content -Path $tmpWin -Value $cmd -Encoding ASCII
wsl -e sh $tmpWsl
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
