#!/bin/sh
set -eu

ack=${1:-}
root=/tmp/w3-qdrv-hostlink-core
control=/sys/devices/qdrv/control
single=/sys/module/qdrv/parameters/openmitrastar_single_vap_create
rf=/sys/module/qdrv/parameters/openmitrastar_rf_enable
stop() { code=$1; shift; echo "W3_QDRV_HOSTLINK_VAP_STOP code=$code $*" >/dev/console; exit "$code"; }

test "$ack" = OPENMITRASTAR_QTN_W3_HOSTLINK_VAP_ONCE_RAM_ONLY || stop 151 reason=ack
test "$(cat /run/openmitrastar/switch-emac-handoff/status)" = committed || stop 152 reason=switch
management_path=
if test -e /sys/class/net/br0/brif/eth1_emac1; then
	management_path=vendor-switch-emac
elif test -e /sys/class/net/br0/brif/eth0 &&
	 dmesg | grep -Fq 'OMEMACSW stage=symbols-only-ready target=mitrastar,hgw-500bna-qcv2'; then
	management_path=direct-emac-preserved
else
	stop 152 reason=management
fi
grep -q '^qdrv ' /proc/modules || stop 152 reason=qdrv
test ! -e /sys/class/net/wifi0 || stop 152 reason=preexisting_wifi0
test "$(cat "$single")" = 0 || stop 152 reason=single_vap_not_zero
test "$(cat "$rf")" = 0 || stop 152 reason=rf_open
dmesg | grep -Eq 'OMQDRVHLINK stage=complete .*cmd=19 .*rc=1' || stop 152 reason=cmd19_not_proven
! dmesg | grep -Eq 'MuC exception|forcing reboot|Kernel panic|Oops:|BUG:|Unable to handle' || stop 152 reason=fatal_preexisting

mac_file=$root/private/mac0addr
test -f "$mac_file" || stop 153 reason=mac_missing
mac=$(sed -n '1{s/\r$//;p;}' "$mac_file")
test "${#mac}" = 17 || stop 153 reason=mac_invalid
before=$(dmesg | wc -l)
printf '1\n' >"$single" || stop 154 reason=enable_single_vap
test "$(cat "$single")" = 1 || stop 154 reason=single_vap_readback
printf 'start 0 ap wifi0 %s\n' "$mac" >"$control" || stop 154 reason=vap_control_write
unset mac
reply=$(cat "$control" 2>/dev/null || true)
test "$reply" = ok || stop 154 reason=vap_control_reply reply="$reply"
sleep 1

after=$(dmesg | wc -l)
new=$((after - before))
test "$new" -gt 0 || stop 155 reason=no_dmesg
dmesg | tail -n "$new" >"$root/vap.dmesg"
grep -Eq 'OMQDRVHLINK stage=publish .*cmd=4 .*published=0x4[0-9a-f]+' "$root/vap.dmesg" || stop 155 reason=cmd4_publish
grep -Eq 'OMQDRVHLINK stage=complete .*cmd=4 .*rc=1' "$root/vap.dmesg" || stop 155 reason=cmd4_complete
grep -Fq 'OMQDRVSEQ stage=vap-pass unit=0 mode=ap interface=wifi0 rf=blocked count=1' "$root/vap.dmesg" || stop 155 reason=vap_marker
! grep -Eq 'HLINK MSG timed out.*cmd=4|MuC exception|forcing reboot|Kernel panic|Oops:|BUG:|Unable to handle' "$root/vap.dmesg" || stop 155 reason=fatal
test -e /sys/class/net/wifi0 || stop 155 reason=wifi0_absent
test "$(cat /sys/class/net/wifi0/operstate)" = down || stop 155 reason=wifi0_not_down
test "$(cat "$rf")" = 0 || stop 155 reason=rf_changed
count=$(ls -d /sys/class/net/wifi* 2>/dev/null | wc -l)
test "$count" = 1 || stop 155 reason=vap_count count="$count"
case "$management_path" in
	vendor-switch-emac) test -e /sys/class/net/br0/brif/eth1_emac1 || stop 155 reason=management_lost ;;
	direct-emac-preserved) test -e /sys/class/net/br0/brif/eth0 || stop 155 reason=management_lost ;;
esac
echo "W3_QDRV_HOSTLINK_VAP_PASS=1 wifi0=down rf=blocked management=$management_path" >/dev/console
echo W3_QDRV_HOSTLINK_VAP_EXPERIMENT_PASS=1
