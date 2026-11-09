#!/bin/ash
# One normal F365 startup in RAM; never flash, reboot, arm watchdog or unload.
set +x
set -eu
umask 077
base=/run/openmitrastar/f365-ram-20261021-r3
PATH=$base/bin:/sbin:/bin:/usr/sbin:/usr/bin
export PATH
boot=5f513265-a294-4366-9567-e1d8af704b6b
store=fcbeb5ab9f1fde273632a0f1a2f0a5d8b1304aa361439c24d1fe8e29cbb1c873
config=073747246e193ebca532b2de35b78a27a1930a908e0717f5706a682fa44457a9
state=$base/state
export OM_RADIO5_MODULE_DIR=$base/modules OM_RADIO5_SHARE=$base/share
export OM_RADIO5_STOP=$base/bin/om-radio5-stop OM_RADIO5_STATE=$state
export OM_RADIO5_LOG_PATH=$base/events
die() { printf 'OMF365_RAM_REFUSED reason=%s\n' "$1"; exit 31; }
wdt() {
  /usr/sbin/om-watchdog-supervisor --inspect | awk '
    /"event"[ ]*:[ ]*"inspect"/ {event=1}
    /"device_opened"[ ]*:[ ]*0/ {closed=1}
    /"control_valid"[ ]*:[ ]*1/ {valid=1}
    /"control"[ ]*:[ ]*"00000000"/ {inactive=1}
    END {exit !(event&&closed&&valid&&inactive)}'
}
preserved() {
  [ "$(cat /proc/sys/kernel/random/boot_id)" = "$boot" ] || die boot-epoch
  [ "$(sha256sum /dev/mtd4 | awk '{print $1}')" = "$store" ] || die store-changed
  [ "$(sha256sum /run/openmitrastar/config/active.conf | awk '{print $1}')" = "$config" ] || die config-changed
  wdt || die watchdog-active
  [ -e /sys/class/net/br0/brif/eth0 ] && [ -e /sys/class/net/br0/brif/wlan0 ] || die management-topology
  /usr/sbin/hostapd_cli -p /run/openmitrastar/radio2g/ctrl -i wlan0 status | grep -qx state=ENABLED || die radio2g-inactive
  printf 'OMF365_RAM_PRESERVED boot=1 store=1 config=1 watchdog=0 management=1 radio2g=1\n'
}
preflight() {
  [ "$(id -u)" = 0 ] || die root-required
  [ "$(uname -r)" = 5.10.260-openmitrastar-radiohw ] || die kernel-release
  grep -qx OPENMITRASTAR_PRODUCT_VERSION=lyoko-foundation-6.11.8-f367r9-transition-observation-device /etc/openmitrastar/release || die release
  grep -aq mitrastar,hgw-500bna-qcv2 /proc/device-tree/compatible || die target
  [ "$(cat /run/openmitrastar/boot-state)" = ready ] || die boot-state
  [ ! -e "$base/activation-claimed" ] || die single-activation-only
  for p in /sys/class/net/wifi0 /sys/module/qtn_radar_f367 /sys/module/qtn_radar_f366 /run/openmitrastar/watchdog/owner.lock /run/openmitrastar/watchdog/supervisor.sock; do [ ! -e "$p" ] || die runtime-owner; done
  for m in qdrv wlan qtn_pm_qos_compat qtn_platform_support board_compat runtime_compat iputil dmautil switch_vlan fwt_if hbm topaz_congest_queue emac_lib dpi switch_tqe switch_emac temp_sensor wlan_scan_ap wlan_ccmp wlan_xauth; do ! grep -Eq "^$m " /proc/modules || die dirty-module; done
  ! dmesg | grep -Eq 'MuC.*exception|MuC has halted|Kernel panic|Oops:|BUG:|EV_TLB|EV_ProtV|Misaligned Access' || die fatal-before
  while read -r digest path; do [ "$(sha256sum "$path" | awk '{print $1}')" = "$digest" ] || die artifact-hash; done < "$base/share/artifacts.sha256"
  for f in head tail; do [ -x "$base/bin/$f" ] || die head-tail-missing; done
  preserved
  printf 'OMF365_RAM_PREFLIGHT_PASS channel=36 bandwidth=80 native_radar=0 watchdog_arm=0 unload=0\n'
}
stop() {
  /bin/ash "$base/bin/om-radio5-stop" ram-bounded-stop >/dev/null 2>&1 || true
  rf=$(cat /sys/module/qdrv/parameters/openmitrastar_rf_enable 2>/dev/null || printf absent)
  flags=$(cat /sys/class/net/wifi0/flags 2>/dev/null || printf 0)
  [ "$rf" = 0 ] || [ "$rf" = absent ] || die rf-stop-unverified
  [ "$((flags & 1))" -eq 0 ] || die interface-stop-unverified
  [ ! -e /sys/class/net/br0/brif/wifi0 ] || die bridge-stop-unverified
  ! /usr/sbin/hostapd-cli-qtn -p /var/run/hostapd -i wifi0 ping 2>/dev/null | grep -qx PONG || die hostapd-stop-unverified
  preserved
  printf 'OMF365_RAM_STOP_PASS rf=0 wifi0=down bridge=detached hostapd=down modules=retained\n'
}
inspect() {
  preserved
  rf=$(cat /sys/module/qdrv/parameters/openmitrastar_rf_enable 2>/dev/null || printf absent)
  case "$rf" in 0|1|absent) ;; *) die rf-invalid;; esac
  flags=$(cat /sys/class/net/wifi0/flags 2>/dev/null || printf 0)
  carrier=$(cat /sys/class/net/wifi0/carrier 2>/dev/null || printf 0)
  freq=$(/usr/sbin/iwconfig-qtn wifi0 2>/dev/null | sed -n 's/.*Frequency:\([0-9.]*\) GHz.*/\1/p' | head -n 1)
  case "$freq" in 5.18) channel=36;; '') channel=absent;; *) stop; die non36-readback;; esac
  hostapd=0; /usr/sbin/hostapd-cli-qtn -p /var/run/hostapd -i wifi0 ping 2>/dev/null | grep -qx PONG && hostapd=1
  printf 'OMF365_RAM_STATE rf=%s flags=%s carrier=%s channel=%s hostapd=%s\n' "$rf" "$flags" "$carrier" "$channel" "$hostapd"
  [ "$rf" = 1 ] && [ "$((flags & 1))" -eq 1 ] && [ "$channel" = 36 ] && [ "$hostapd" = 1 ] || return 32
  printf 'OMF365_RAM_CONTROL_PASS channel=36 rf=1 management=1 client=UNRUN traffic=UNRUN\n'
}
activate() {
  [ "${OM_F365_RAM_AUTH_BOOT:-}" = "$boot" ] || die root-authority-binding-required
  preflight
  (set -C; : > "$base/activation-claimed") || die single-activation-only
  mkdir -p "$state"; chmod 0700 "$state"
  # Always retain hardware timeout until root explicitly reviews and keeps this AP.
  (sleep 240; [ -e "$base/keep-running" ] || /bin/ash "$base/bin/guard" stop > "$base/deadline-stop.result" 2>&1) &
  printf '%s\n' "$!" > "$base/deadline.pid"
  # FIFO avoids retaining calibration/client/credential stdout from donor tools.
  /bin/mknod "$base/events" p
  /bin/mknod "$base/starter-output" p
  for f in events starter-output; do
    awk '/^OMRADIO5_/ {s=$0;gsub(/ssid=[^ ]*/,"ssid=redacted",s);gsub(/[0-9A-Fa-f][0-9A-Fa-f]:[0-9A-Fa-f][0-9A-Fa-f]:[0-9A-Fa-f][0-9A-Fa-f]:[0-9A-Fa-f][0-9A-Fa-f]:[0-9A-Fa-f][0-9A-Fa-f]:[0-9A-Fa-f][0-9A-Fa-f]/,"mac=redacted",s); print s;fflush()}' < "$base/$f" > "$base/$f.redacted" &
    printf '%s\n' "$!" >> "$base/redactors.pid"
  done
  # Hold both writers open: event log opens/closes its pipe once per line.
  exec 7>"$base/events" 8>"$base/starter-output"
  /bin/ash "$base/bin/om-radio5-start" > "$base/starter-output" 2>&1 &
  pid=$!; printf '%s\n' "$pid" > "$base/starter.pid"
  (exec 7>&- 8>&-; sleep 115; if kill -0 "$pid" 2>/dev/null; then /bin/ash "$base/bin/guard" stop >/dev/null 2>&1; kill "$pid" 2>/dev/null || true; fi) &
  timer=$!
  rc=0; wait "$pid" || rc=$?
  kill "$timer" 2>/dev/null || true
  exec 7>&- 8>&-
  printf 'OMF365_RAM_START_EXIT rc=%s\n' "$rc"
  [ "$rc" = 0 ] || { stop; return 33; }
  inspect || { stop; return 34; }
  printf 'OMF365_RAM_ACTIVATION_PASS control=1 client=UNRUN traffic=UNRUN module_replace=UNPROVEN deadline=240\n'
}
case "${1:-}" in preflight) preflight;; activate) activate;; inspect) inspect;; stop) stop;; *) die action-required;; esac
