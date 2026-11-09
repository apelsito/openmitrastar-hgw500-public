#!/bin/sh
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
qemu=${QEMU_ARC_BIN:-/home/user/qemu-arc-build2/qemu-system-arc}
kernel=${QEMU_ARC_KERNEL:-/home/user/openmitrastar-build/qemu-arc-validation/vmlinux}
log="$root/outputs/kernel-port/linux-5.10.260-qemu-arc700-validation.serial.log"
trace="$root/outputs/kernel-port/linux-5.10.260-qemu-arc700-validation.qemu-trace.log"

test -x "$qemu"
test -f "$kernel"
set +e
timeout 20s "$qemu" -M arc-sim -cpu arc700 -m 3G -display none \
	-monitor none -no-reboot -serial stdio -d in_asm,guest_errors,unimp \
	-D "$trace" -kernel "$kernel" >"$log" 2>&1
qemu_status=$?
set -e
printf 'QEMU_STATUS=%s\n' "$qemu_status" >>"$log"
grep -q 'OpenMitraStar QEMU validation twin is alive' "$log"
printf 'QEMU validation marker reached (timeout status %s expected after PID 1 pause).\n' \
	"$qemu_status"
