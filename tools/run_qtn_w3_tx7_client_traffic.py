#!/usr/bin/env python3
"""Run the minimal RAM-only 5 GHz client datapath gate on an already-live TX7.

The embedded Quantenna stack is used in place: no reboot, module upload, MTD,
bootenv or flash operation occurs.  The target-local rollback stops wifi0 only;
direct eth0 and the existing wlan0 AP remain untouched.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
ACK = "OPENMITRASTAR_QTN_W3_TX7_CLIENT_TRAFFIC_RAM_ONLY"
RELEASE = "5.10.260-openmitrastar-radiohw"
IMAGE = ROOT / "work/tftp/omvl/linux510-w2-2g-parity-tx7-hybrid32-v1-RAM-TEST-NO-FLASH.bin"
MANIFEST = ROOT / "work/mission-state/w2-2g-parity-tx7-hybrid32-v1/build/manifest.json"
IMAGE_SHA256 = "d547524667d3c1f59b4a4dbf891c1271fe837ee3b5649682a6095492a45781a3"
SAFE_QDRV_SHA256 = "a4a4e277bf815e8b408594d67a1d1afcec03251af5bc4d05b51567abbb41ef33"
QDRV_PROFILE_SHA256 = SAFE_QDRV_SHA256
QDRV_SHA256 = SAFE_QDRV_SHA256
WLAN_SHA256 = "09c5e347f6c0fa9acad4a7e0e3571d5d976a2cf4a5f0e304730eb825badbc872"
HBM_SHA256 = "f3b8b78ffda138c5c8287c923086c51cd896e51539ff7a17caa394c0bc6cebb8"
SWITCH_TQE_SHA256 = "368c347eac8fdf895cc4ec37c394a0a97b4c0297f892a506bf5986a21e532c74"
BOARD_COMPAT_SHA256 = "0969752af8257a03a6951b82c5e1a269f4aeb99036e38cf6a781cf1a58cef97d"
SWITCH_EMAC_SHA256 = "9c45dcf6300b1ac668b73c3fce92d8e6f25599604850a293bbac0f0e58992c87"
BASE_QDRV_SHA256 = "9ba6cd3ff63e23fb03fc8e8d5cd6e93f9d710e0d56a0693852f4227cf9dabb20"
BASE_WLAN_SHA256 = "d286d8f5792193ad4c4c63e4d4a23e7e540e56184aafb765b393fd4ae01ed48b"
BASE_HBM_SHA256 = "c5084d18167b20f250718c2e97ad94bf36f059543eb37d7372513352b3aa357b"
BASE_SWITCH_TQE_SHA256 = "29be629fc1091428a7e63cd80030635f0038eaf0214dfd5bbf5dfa66ef079d63"
F38_QDRV_SHA256 = "cf02ec450a676d34ac072ceac3057b90f6833d7d129ece1b77e4193ea6ece411"
F38_WLAN_SHA256 = "b8dea7d8c15539004e4a41ca95f05e12cd3cb7c13e941346a2405c4cfc707fb5"
F38_HBM_SHA256 = "e5358d3ba585747735a12d2d3313d413f733f20016b0130c786d53c6715362a6"
F38_SWITCH_TQE_SHA256 = "1f2e7e8abe9ce08571ca97fdc39123d0c7c146c09b8a1e0ae657b72487f2b8a1"
SAFE_OVERLAY = "/run/openmitrastar/w3-qtn-safe"
SAFE_START = (
    ROOT / "outputs/kernel-port/quantenna-5g-isolated-l3-runtime-20260823/om-radio5-start-isolated-l3",
    "e5298e36a8bbc6d68c013ba14a1a246db4379f09d222d4b52c0bed07f1321d89",
)
SAFE_STOP = (
    ROOT / "outputs/kernel-port/quantenna-5g-isolated-l3-runtime-20260823/om-radio5-stop-isolated-l3",
    "2f4983b7ae02a89ea55472b2ed59da67a59e90d1a57c503d8838e43894348444",
)
SAFE_LOADER = (
    ROOT / "work/mission-state/q3-calibration-overlay/inspect-20260821-1645/usr/sbin/ram-insmod-qtn",
    "8eb902dcc5e1bdab1aba356aafca04102ab394352c1685434ac9a9a09c5baba6",
)
SAFE_MODULES = {
    "qdrv.ko": (
        ROOT / "outputs/kernel-port/quantenna-linux510-radiohw-calibration-20260821/rootfs/lib/modules/5.10.260-openmitrastar-radiohw/extra/quantenna/qdrv/qdrv.ko",
        QDRV_SHA256,
    ),
    "wlan.ko": (
        ROOT / "outputs/kernel-port/quantenna-linux510-radiohw-calibration-rtnl-20260821/rootfs/lib/modules/5.10.260-openmitrastar-radiohw/extra/quantenna/wlan/wlan.ko",
        WLAN_SHA256,
    ),
    "hbm.ko": (
        ROOT / "outputs/kernel-port/qtn-hbm-clear-probe-20260821/hbm.ko",
        HBM_SHA256,
    ),
    "switch_tqe.ko": (
        ROOT / "outputs/kernel-port/qtn-switch-tqe-dma-device-fix-20260821/switch_tqe.ko",
        SWITCH_TQE_SHA256,
    ),
    "board_compat.ko": (
        ROOT / "work/mission-state/q3-calibration-overlay/inspect-20260821-1645/lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio5g/board_compat.ko",
        BOARD_COMPAT_SHA256,
    ),
    "switch_emac.ko": (
        ROOT / "work/mission-state/q3-calibration-overlay/inspect-20260821-1645/lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio5g/switch_emac.ko",
        SWITCH_EMAC_SHA256,
    ),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(command: list[str], timeout: int, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command, cwd=ROOT, text=True, capture_output=True,
        timeout=timeout, check=False,
    )
    if check and result.returncode:
        raise RuntimeError(
            "command failed rc="
            f"{result.returncode}: {' '.join(command)}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
    return result


def ssh(host: str, command: str, timeout: int = 30, check: bool = True) -> subprocess.CompletedProcess[str]:
    return run(
        [sys.executable, "tools/ramssh_exec.py", command,
         "--host", host, "--timeout", str(timeout)],
        timeout=timeout + 20, check=check,
    )


def verify_local() -> dict[str, object]:
    if not IMAGE.is_file() or sha256(IMAGE) != IMAGE_SHA256:
        raise SystemExit("TX7 image identity mismatch")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if manifest.get("classification") != "RAM-ONLY-W2-2G-PARITY-TX7-HYBRID32-NO-FLASH":
        raise SystemExit("TX7 manifest classification mismatch")
    if manifest["artifacts"]["tftp_copy"]["sha256"] != IMAGE_SHA256:
        raise SystemExit("TX7 manifest image hash mismatch")
    if manifest["security"]["radio5g_autostart"] is not False:
        raise SystemExit("TX7 must keep 5 GHz autostart disabled")
    return manifest


def preflight_remote(host: str) -> None:
    module_dir = f"/lib/modules/{RELEASE}/openmitrastar/radio5g"
    command = rf'''set -eu
test "$(uname -r)" = {RELEASE}
test -e /sys/class/net/br0/brif/eth0
test -e /sys/class/net/br0/brif/wlan0
test ! -e /sys/class/net/br0/brif/wifi0
pidfile=
for candidate in /run/openmitrastar/radio2g/hostapd-open.pid /run/openmitrastar/radio2g/hostapd.pid; do
  if [ -s "$candidate" ] && kill -0 "$(cat "$candidate")" 2>/dev/null; then pidfile=$candidate; break; fi
done
[ -n "$pidfile" ]
for module in qdrv wlan hbm switch_tqe switch_emac; do
  ! grep -q "^$module " /proc/modules
done
check_any3() {{
  actual=$(sha256sum "$1" | awk '{{print $1}}')
  [ "$actual" = "$2" ] || [ "$actual" = "$3" ] || [ "$actual" = "$4" ]
}}
check_any4() {{
  actual=$(sha256sum "$1" | awk '{{print $1}}')
  [ "$actual" = "$2" ] || [ "$actual" = "$3" ] || [ "$actual" = "$4" ] || [ "$actual" = "$5" ]
}}
check_any4 {module_dir}/qdrv.ko {BASE_QDRV_SHA256} {SAFE_QDRV_SHA256} {QDRV_SHA256} {F38_QDRV_SHA256}
check_any3 {module_dir}/wlan.ko {BASE_WLAN_SHA256} {WLAN_SHA256} {F38_WLAN_SHA256}
check_any3 {module_dir}/hbm.ko {BASE_HBM_SHA256} {HBM_SHA256} {F38_HBM_SHA256}
check_any3 {module_dir}/switch_tqe.ko {BASE_SWITCH_TQE_SHA256} {SWITCH_TQE_SHA256} {F38_SWITCH_TQE_SHA256}
test -s /usr/share/openmitrastar/radio5g/runtime.env
test -s /usr/share/openmitrastar/radio5g/artifacts.sha256
test -x /usr/sbin/hostapd-qtn
test -x /usr/sbin/hostapd-cli-qtn
test -x /usr/sbin/iwconfig-qtn
test -x /usr/sbin/iwpriv-qtn
test -r /run/openmitrastar/origin-mtd5/ready
test -r /run/openmitrastar/calibration/ready
test -r /run/openmitrastar/secrets/qtn-mac0addr
! dmesg | grep -Eq 'MuC:.*exception|MuC exception|MuC has halted|forcing reboot|Kernel panic|Oops|BUG:|Unable to handle|EV_TLB|EV_ProtV|Misaligned Access|Misaligned r/w|Invalid Read|Invalid Write'
echo OMW3TX7_PREFLIGHT_PASS eth0=1 radio2g=1 pidfile=$pidfile radio5g=clean base_modules=accepted safe_overlay=pending
'''
    result = ssh(host, command, 45)
    if "OMW3TX7_PREFLIGHT_PASS" not in result.stdout:
        raise RuntimeError("TX7 remote preflight marker missing")


def verify_safe_modules() -> None:
    for name, (path, expected) in SAFE_MODULES.items():
        if not path.is_file() or sha256(path) != expected:
            raise RuntimeError(f"safe Quantenna module mismatch: {name}")
    for name, (path, expected) in {
        "om-radio5-start": SAFE_START,
        "om-radio5-stop": SAFE_STOP,
        "ram-insmod-qtn": SAFE_LOADER,
    }.items():
        if not path.is_file() or sha256(path) != expected:
            raise RuntimeError(f"safe Quantenna runtime mismatch: {name}")


def stage_safe_overlay(host: str) -> None:
    verify_safe_modules()
    base = f"/lib/modules/{RELEASE}/openmitrastar/radio5g"
    prepare = rf'''set -eu
root={SAFE_OVERLAY}
base={base}
base_share=/usr/share/openmitrastar/radio5g
rm -rf "$root"
mkdir -p "$root/modules" "$root/share" "$root/upload" "$root/bin"
chmod 0700 "$root" "$root/modules" "$root/share" "$root/upload" "$root/bin"
for file in "$base"/*.ko; do
  [ -f "$file" ] || exit 91
  ln -s "$file" "$root/modules/${{file##*/}}"
done
for file in "$base_share"/*; do
  [ -f "$file" ] && cp "$file" "$root/share/${{file##*/}}"
done
test -s "$root/share/runtime.env"
test -s "$root/share/artifacts.sha256"
echo OMW3SAFE stage=prepared root=$root base=$base flash=0
'''
    result = ssh(host, prepare, 30)
    if "OMW3SAFE stage=prepared" not in result.stdout:
        raise RuntimeError("safe overlay prepare marker missing")

    for name, (source, _) in SAFE_MODULES.items():
        upload = run(
            [sys.executable, "tools/ramssh_upload.py", str(source),
             f"{SAFE_OVERLAY}/upload/{name}", "--host", host, "--mode", "0600"],
            60,
        )
        if "RAMSSH_UPLOAD_OK" not in upload.stdout:
            raise RuntimeError(f"safe module upload marker missing: {name}")
    for name, (source, _) in {
        "om-radio5-start": SAFE_START,
        "om-radio5-stop": SAFE_STOP,
        "ram-insmod-qtn": SAFE_LOADER,
    }.items():
        upload = run(
            [sys.executable, "tools/ramssh_upload.py", str(source),
             f"{SAFE_OVERLAY}/upload/{name}", "--host", host, "--mode", "0600"],
            60,
        )
        if "RAMSSH_UPLOAD_OK" not in upload.stdout:
            raise RuntimeError(f"safe runtime upload marker missing: {name}")

    activate = rf'''set -eu
root={SAFE_OVERLAY}
overlay="$root/modules"
share="$root/share"
check() {{ test "$(sha256sum "$1" | awk '{{print $1}}')" = "$2"; }}
echo OMW3SAFE stage=activate-check-uploads
check "$root/upload/qdrv.ko" {QDRV_SHA256}
check "$root/upload/wlan.ko" {WLAN_SHA256}
check "$root/upload/hbm.ko" {HBM_SHA256}
check "$root/upload/switch_tqe.ko" {SWITCH_TQE_SHA256}
check "$root/upload/board_compat.ko" {BOARD_COMPAT_SHA256}
check "$root/upload/switch_emac.ko" {SWITCH_EMAC_SHA256}
check "$root/upload/om-radio5-start" {SAFE_START[1]}
check "$root/upload/om-radio5-stop" {SAFE_STOP[1]}
check "$root/upload/ram-insmod-qtn" {SAFE_LOADER[1]}
echo OMW3SAFE stage=activate-move-modules
for name in qdrv.ko wlan.ko hbm.ko switch_tqe.ko board_compat.ko switch_emac.ko; do
  rm -f "$overlay/$name"
  mv "$root/upload/$name" "$overlay/$name"
  chmod 0600 "$overlay/$name"
done
mv "$root/upload/om-radio5-stop" "$root/bin/om-radio5-stop"
mv "$root/upload/ram-insmod-qtn" "$root/bin/ram-insmod-qtn"
mv "$root/upload/om-radio5-start" "$root/bin/om-radio5-start"
chmod 0700 "$root/bin/om-radio5-start" "$root/bin/om-radio5-stop" "$root/bin/ram-insmod-qtn"
echo OMW3SAFE stage=activate-rewrite-runtime
awk -F= -v q={QDRV_PROFILE_SHA256} -v w={WLAN_SHA256} -v h={HBM_SHA256} -v t={SWITCH_TQE_SHA256} -v b={BOARD_COMPAT_SHA256} -v s={SWITCH_EMAC_SHA256} '
  $1=="Q3_QDRV_SHA256"{{$0="Q3_QDRV_SHA256=" q; sq=1}}
  $1=="Q3_WLAN_SHA256"{{$0="Q3_WLAN_SHA256=" w; sw=1}}
  $1=="Q3_HBM_SHA256"{{$0="Q3_HBM_SHA256=" h; sh=1}}
  $1=="Q3_SWITCH_TQE_SHA256"{{$0="Q3_SWITCH_TQE_SHA256=" t; st=1}}
  $1=="Q3_BOARD_COMPAT_SHA256"{{$0="Q3_BOARD_COMPAT_SHA256=" b; sb=1}}
  $1=="Q3_SWITCH_EMAC_SHA256"{{$0="Q3_SWITCH_EMAC_SHA256=" s; ss=1}}
  {{print}}
  END {{
    if (!sq) print "Q3_QDRV_SHA256=" q
    if (!sw) print "Q3_WLAN_SHA256=" w
    if (!sh) print "Q3_HBM_SHA256=" h
    if (!st) print "Q3_SWITCH_TQE_SHA256=" t
    if (!sb) print "Q3_BOARD_COMPAT_SHA256=" b
    if (!ss) print "Q3_SWITCH_EMAC_SHA256=" s
  }}
' "$share/runtime.env" >"$share/runtime.env.new"
mv "$share/runtime.env.new" "$share/runtime.env"
echo OMW3SAFE stage=activate-rewrite-artifacts
awk -v o="$overlay" -v b="$root/bin" -v q={QDRV_SHA256} -v w={WLAN_SHA256} -v h={HBM_SHA256} -v t={SWITCH_TQE_SHA256} -v bc={BOARD_COMPAT_SHA256} -v se={SWITCH_EMAC_SHA256} -v l={SAFE_LOADER[1]} '
  /\/qdrv[.]ko$/ {{print q " " o "/qdrv.ko"; sq=1; next}}
  /\/wlan[.]ko$/ {{print w " " o "/wlan.ko"; sw=1; next}}
  /\/hbm[.]ko$/ {{print h " " o "/hbm.ko"; sh=1; next}}
  /\/switch_tqe[.]ko$/ {{print t " " o "/switch_tqe.ko"; st=1; next}}
  /\/board_compat[.]ko$/ {{print bc " " o "/board_compat.ko"; sb=1; next}}
  /\/switch_emac[.]ko$/ {{print se " " o "/switch_emac.ko"; ss=1; next}}
  /\/ram-insmod-qtn$/ {{print l " " b "/ram-insmod-qtn"; sl=1; next}}
  {{print}}
  END {{
    if (!sq) print q " " o "/qdrv.ko"
    if (!sw) print w " " o "/wlan.ko"
    if (!sh) print h " " o "/hbm.ko"
    if (!st) print t " " o "/switch_tqe.ko"
    if (!sb) print bc " " o "/board_compat.ko"
    if (!ss) print se " " o "/switch_emac.ko"
    if (!sl) print l " " b "/ram-insmod-qtn"
  }}
' "$share/artifacts.sha256" >"$share/artifacts.sha256.new"
mv "$share/artifacts.sha256.new" "$share/artifacts.sha256"
echo OMW3SAFE stage=activate-check-staged
check "$overlay/qdrv.ko" {QDRV_SHA256}
check "$overlay/wlan.ko" {WLAN_SHA256}
check "$overlay/hbm.ko" {HBM_SHA256}
check "$overlay/switch_tqe.ko" {SWITCH_TQE_SHA256}
check "$overlay/board_compat.ko" {BOARD_COMPAT_SHA256}
check "$overlay/switch_emac.ko" {SWITCH_EMAC_SHA256}
check "$root/bin/om-radio5-stop" {SAFE_STOP[1]}
check "$root/bin/ram-insmod-qtn" {SAFE_LOADER[1]}
check "$root/bin/om-radio5-start" {SAFE_START[1]}
echo OMW3SAFE stage=activate-check-start
grep -Fq 'OMQTN5G_ISOLATED_L3_RUNTIME=1' "$root/bin/om-radio5-start"
! grep -Fq 'brctl addif br0 wifi0' "$root/bin/om-radio5-start"
echo OMW3SAFE stage=activate-check-runtime
grep -qx 'Q3_QDRV_SHA256={QDRV_PROFILE_SHA256}' "$share/runtime.env"
grep -qx 'Q3_WLAN_SHA256={WLAN_SHA256}' "$share/runtime.env"
grep -qx 'Q3_HBM_SHA256={HBM_SHA256}' "$share/runtime.env"
grep -qx 'Q3_SWITCH_TQE_SHA256={SWITCH_TQE_SHA256}' "$share/runtime.env"
grep -qx 'Q3_BOARD_COMPAT_SHA256={BOARD_COMPAT_SHA256}' "$share/runtime.env"
grep -qx 'Q3_SWITCH_EMAC_SHA256={SWITCH_EMAC_SHA256}' "$share/runtime.env"
echo OMW3SAFE stage=active qdrv={QDRV_SHA256} qdrv_profile={QDRV_PROFILE_SHA256} wlan={WLAN_SHA256} hbm={HBM_SHA256} switch_tqe={SWITCH_TQE_SHA256} start=staged stop=staged loader=staged flash=0
'''
    result = ssh(host, activate, 45)
    if "OMW3SAFE stage=active" not in result.stdout:
        raise RuntimeError("safe overlay activation marker missing")


def cleanup_safe_overlay(host: str) -> None:
    ssh(host, f"rm -rf {SAFE_OVERLAY}; echo OMW3SAFE_CLEANUP_PASS flash=0", 20, check=False)


def collect_radio5_failure_snapshot(host: str, output: Path, run_id: str = "manual") -> None:
    run_id = validate_run_id(run_id)
    output.parent.mkdir(parents=True, exist_ok=True)
    command = rf'''set +e
echo OMW3TX7_FAILURE_SNAPSHOT_BEGIN run_id={run_id}
echo SECTION_FAILURE_LATEST
latest=/run/openmitrastar/radio5g-failures/latest
if [ -r "$latest" ]; then
  failure_dir=$(cat "$latest" 2>/dev/null)
  echo latest="$failure_dir"
  if [ -r "$failure_dir/diagnostic.txt" ]; then
    cat "$failure_dir/diagnostic.txt"
  fi
else
  echo latest=missing
fi
echo SECTION_RADIO5_STATE
for name in state last-refusal hostapd.pid rollback.pid auc-tx-set.log; do
  file=/run/openmitrastar/radio5g/$name
  if [ -r "$file" ]; then
    printf '%s=' "$name"
    sed -n '1,40p' "$file" 2>/dev/null | tr '\n' ' '
    printf '\n'
  fi
done
echo SECTION_NET
ifconfig wifi0 2>/dev/null || true
ifconfig wlan0 2>/dev/null || true
ifconfig br0 2>/dev/null || true
ls -1 /sys/class/net/br0/brif 2>/dev/null || true
echo SECTION_MODULES
cat /proc/modules 2>/dev/null | grep -E '^(qdrv|wlan|hbm|switch_tqe|switch_emac|topaz_congest_queue|fwt_if|emac_lib|dpi|runtime_compat|iputil|dmautil|switch_vlan|board_compat|qtn_platform_support|qtn_pm_qos_compat|wlan_scan_ap|wlan_ccmp|wlan_xauth|rtl8192ee|rtl_pci|rtlwifi|mac80211|cfg80211) ' || true
echo SECTION_DMESG_QTN
dmesg 2>/dev/null | grep -E 'OMRADIO5|OMQTN5G|OMW3|OMQDRV|qdrv|MuC|AuC|switch_tqe|hbm|wifi0|hostapd|REFUSED|refused|panic|Oops|BUG|EV_TLB|EV_ProtV|Misaligned' | tail -n 320 || true
echo OMW3TX7_FAILURE_SNAPSHOT_END run_id={run_id}
'''
    result = ssh(host, command, 45, check=False)
    output.write_text(
        "COMMAND_RC={}\nSTDOUT_BEGIN\n{}STDOUT_END\nSTDERR_BEGIN\n{}STDERR_END\n".format(
            result.returncode,
            result.stdout or "",
            result.stderr or "",
        ),
        encoding="utf-8",
        newline="\n",
    )


def stop_radio5(host: str, reason: str) -> None:
    command = rf'''set +e
gate=/run/openmitrastar/w3-tx7-client-gate
stop={SAFE_OVERLAY}/bin/om-radio5-stop
[ -x "$stop" ] || stop=/usr/sbin/om-radio5-stop
[ -x "$stop" ] && "$stop" {reason}
[ ! -r "$gate/console-loglevel.original" ] || cat "$gate/console-loglevel.original" >/proc/sys/kernel/printk
echo OMW3SAFE_STOP_DONE reason={reason} radio2g=preserved flash=0
'''
    ssh(host, command, 30, check=False)


def validate_run_id(run_id: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,80}", run_id):
        raise ValueError("unsafe run_id")
    return run_id


def prepare_radio5_gate(host: str, run_id: str = "manual") -> None:
    run_id = validate_run_id(run_id)
    command = rf'''set -eu
emit_marker() {{
  if [ -w /dev/kmsg ]; then printf '<6>%s\n' "$*" >/dev/kmsg; else printf '%s\n' "$*" >/dev/console; fi
}}
gate=/run/openmitrastar/w3-tx7-client-gate
rm -rf "$gate"
mkdir -p "$gate"
chmod 0700 "$gate"
printf '%s\n' Q3_RADIO5_OPEN_LAB=1 >"$gate/open-lab.feature"
printf '%s\n' Q3_RADIO5_BEACON_LIFETIME=1 >"$gate/beacon-lifetime.feature"
printf '%s\n' Q3_RADIO5_TQE_RING_ENTRIES=512 >"$gate/tqe512.feature"
printf '%s\n' '{run_id}' >"$gate/run-id"
chmod 0600 "$gate"/*.feature
chmod 0600 "$gate/run-id"
console_loglevel=$(cut -d' ' -f1 /proc/sys/kernel/printk)
printf '%s\n' "$console_loglevel" >"$gate/console-loglevel.original"
chmod 0600 "$gate/console-loglevel.original"
if [ "$console_loglevel" -lt 6 ]; then
  echo 6 >/proc/sys/kernel/printk
fi
active_console_loglevel=$(cut -d' ' -f1 /proc/sys/kernel/printk)
if [ "$active_console_loglevel" -lt 6 ]; then
  cat "$gate/console-loglevel.original" >/proc/sys/kernel/printk
  echo OMW3TX7_GATE_REFUSED reason=console-loglevel value="$active_console_loglevel"
  exit 1
fi
emit_marker 'OMQTN5G_RUN stage=begin run_id={run_id}'
echo OMW3TX7_GATE_PREPARED run_id={run_id} rollback=pending console_loglevel="$active_console_loglevel" original_console_loglevel="$console_loglevel"
'''
    result = ssh(host, command, 20)
    if "OMW3TX7_GATE_PREPARED" not in result.stdout:
        raise RuntimeError("TX7 gate preparation marker missing")


def start_radio5(host: str, run_id: str = "manual") -> str:
    run_id = validate_run_id(run_id)
    command = rf'''set -eu
emit_marker() {{
  if [ -w /dev/kmsg ]; then printf '<6>%s\n' "$*" >/dev/kmsg; else printf '%s\n' "$*" >/dev/console; fi
}}
gate=/run/openmitrastar/w3-tx7-client-gate
test "$(cat "$gate/run-id")" = '{run_id}'
test -r "$gate/open-lab.feature"
test -r "$gate/beacon-lifetime.feature"
test -r "$gate/tqe512.feature"
emit_marker 'OMQTN5G_RUN stage=qdrv-load-begin run_id={run_id}'
OM_RADIO5_OPEN_LAB_FEATURE="$gate/open-lab.feature" \
OM_RADIO5_BEACON_LIFETIME_FEATURE="$gate/beacon-lifetime.feature" \
OM_RADIO5_TQE512_FEATURE="$gate/tqe512.feature" \
OM_RADIO5_MODULE_DIR="{SAFE_OVERLAY}/modules" \
OM_RADIO5_SHARE="{SAFE_OVERLAY}/share" \
OM_RADIO5_LOADER="{SAFE_OVERLAY}/bin/ram-insmod-qtn" \
OM_RADIO5_STOP="{SAFE_OVERLAY}/bin/om-radio5-stop" \
  "{SAFE_OVERLAY}/bin/om-radio5-start"
emit_marker 'OMQTN5G_RUN stage=qdrv-load-pass run_id={run_id}'
test -r /run/openmitrastar/radio5g/ready
test -e /sys/class/net/br0/brif/eth0
test -e /sys/class/net/br0/brif/wlan0
test ! -e /sys/class/net/br0/brif/wifi0
ifconfig wifi0 2>/dev/null | grep -q '192.168.77.1'
test "$(cat /sys/module/switch_tqe/parameters/w3_rx_ring_entries)" = 512
echo OMW3TX7_MODULE_MAP_BEGIN
cat /proc/modules
for module in hbm topaz_congest_queue switch_tqe fwt_if switch_emac qdrv wlan wlan_scan_ap wlan_ccmp wlan_xauth rtl8192ee rtl_pci rtlwifi; do
  printf '%s=' "$module"
  cat "/sys/module/$module/sections/.text" 2>/dev/null || echo missing
done
echo OMW3TX7_MODULE_MAP_END
echo OMW3TX7_AP_START_PASS ssid=OpenMitraStar-5G-DIAG eth0=1 radio2g=1 safe_overlay=1 tqe_ring=512 isolated_l3=192.168.77.1/24 br0_wifi0=0 flash=0
'''
    result = ssh(host, command, 180)
    if "OMW3TX7_AP_START_PASS" not in result.stdout:
        raise RuntimeError("TX7 5 GHz start marker missing")
    return result.stdout


def arm_rollback(host: str, seconds: int, run_id: str = "manual") -> None:
    run_id = validate_run_id(run_id)
    command = rf'''set -eu
gate=/run/openmitrastar/w3-tx7-client-gate
test "$(cat "$gate/run-id")" = '{run_id}'
if [ -s "$gate/rollback.pid" ]; then
  kill "$(cat "$gate/rollback.pid")" 2>/dev/null || true
fi
rm -f "$gate/commit" "$gate/rollback.pid"
( sleep {seconds}; if [ ! -e "$gate/commit" ]; then
    set +e
    if [ -w /dev/kmsg ]; then echo '<6>OMQTN5G_RUN stage=rollback-begin run_id={run_id}' >/dev/kmsg; else echo 'OMQTN5G_RUN stage=rollback-begin run_id={run_id}' >/dev/console; fi
    {SAFE_OVERLAY}/bin/om-radio5-stop tx7-client-gate-timeout >/dev/console 2>&1
    stop_rc=$?
    restore_rc=0
    if [ -r "$gate/console-loglevel.original" ]; then
      original=$(cat "$gate/console-loglevel.original")
      echo "$original" >/proc/sys/kernel/printk || restore_rc=$?
      restored=$(cut -d' ' -f1 /proc/sys/kernel/printk)
      [ "$restored" = "$original" ] || restore_rc=1
    fi
    if [ -w /dev/kmsg ]; then echo "<6>OMRADIO5_ROLLBACK_COMPLETE run_id={run_id} stop_rc=$stop_rc loglevel_restore_rc=$restore_rc eth0_2g=preserved" >/dev/kmsg; else echo "OMRADIO5_ROLLBACK_COMPLETE run_id={run_id} stop_rc=$stop_rc loglevel_restore_rc=$restore_rc eth0_2g=preserved" >/dev/console; fi
    rm -rf {SAFE_OVERLAY}
  fi ) >/dev/null 2>&1 &
printf '%s\n' "$!" >"$gate/rollback.pid"
chmod 0600 "$gate/rollback.pid"
echo OMW3TX7_ROLLBACK_ARMED run_id={run_id} seconds={seconds} scope=wifi0-only eth0_2g=preserved
'''
    result = ssh(host, command, 20)
    if "OMW3TX7_ROLLBACK_ARMED" not in result.stdout:
        raise RuntimeError("TX7 client rollback marker missing")


def commit(host: str, run_id: str = "manual") -> None:
    run_id = validate_run_id(run_id)
    command = rf'''set -eu
emit_marker() {{
  if [ -w /dev/kmsg ]; then printf '<6>%s\n' "$*" >/dev/kmsg; else printf '%s\n' "$*" >/dev/console; fi
}}
gate=/run/openmitrastar/w3-tx7-client-gate
test "$(cat "$gate/run-id")" = '{run_id}'
test -e /sys/class/net/br0/brif/eth0
test -e /sys/class/net/br0/brif/wlan0
test ! -e /sys/class/net/br0/brif/wifi0
ifconfig wifi0 2>/dev/null | grep -q '192.168.77.1'
[ -r "$gate/console-loglevel.original" ]
original=$(cat "$gate/console-loglevel.original")
echo "$original" >/proc/sys/kernel/printk
restored=$(cut -d' ' -f1 /proc/sys/kernel/printk)
[ "$restored" = "$original" ]
touch "$gate/commit"
chmod 0600 "$gate/commit"
if [ -s "$gate/rollback.pid" ]; then
  kill "$(cat "$gate/rollback.pid")" 2>/dev/null || true
fi
emit_marker 'OMQTN5G_RUN stage=commit run_id={run_id}'
echo OMW3TX7_CLIENT_TRAFFIC_COMMIT_PASS run_id={run_id} eth0=1 radio2g=1 radio5g=1 isolated_l3=1 br0_wifi0=0 flash=0
'''
    result = ssh(host, command, 20)
    if "OMW3TX7_CLIENT_TRAFFIC_COMMIT_PASS" not in result.stdout:
        raise RuntimeError("TX7 client commit marker missing")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--ack")
    parser.add_argument("--host", default="192.168.1.90")
    parser.add_argument("--seconds", type=int, default=180)
    parser.add_argument("--interval", type=int, default=1)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--run-id", default="manual")
    args = parser.parse_args()
    verify_local()
    verify_safe_modules()
    if not 60 <= args.seconds <= 600:
        raise SystemExit("--seconds must be 60..600")
    if not 1 <= args.interval <= 10:
        raise SystemExit("--interval must be 1..10")
    validate_run_id(args.run_id)
    if not args.execute:
        print(json.dumps({
            "mode": "dry-run", "image_sha256": IMAGE_SHA256,
            "host": args.host, "ssid": "OpenMitraStar-5G-DIAG",
            "embedded_switch_tqe_sha256": SWITCH_TQE_SHA256,
            "radio2g_preserved": True, "direct_eth0_preserved": True,
            "single_ssh_monitor": True, "target_local_rollback": True,
            "isolated_l3": True, "router_wifi0": "192.168.77.1/24",
            "flash": False, "reboot": False,
        }, sort_keys=True))
        print("W3_TX7_5G_CLIENT_TRAFFIC_DRY_RUN_PASS=1")
        return 0
    if args.ack != ACK:
        raise SystemExit(f"require --ack {ACK}")
    output = args.output or (
        ROOT / "outputs/uart-live" /
        f"w3-tx7-5g-client-{time.strftime('%Y%m%d-%H%M%S')}.log"
    )
    rollback_seconds = args.seconds + 60
    preflight_remote(args.host)
    overlay_staged = False
    try:
        stage_safe_overlay(args.host)
        overlay_staged = True
        prepare_radio5_gate(args.host, args.run_id)
        arm_rollback(args.host, 240, args.run_id)
        start_output = start_radio5(args.host, args.run_id)
        module_map = output.with_suffix(output.suffix + ".module-map.txt")
        module_map.parent.mkdir(parents=True, exist_ok=True)
        module_map.write_text(start_output, encoding="utf-8", newline="\n")
        arm_rollback(args.host, rollback_seconds, args.run_id)
        monitor = run([
            sys.executable, "tools/q3_client_stream_single_session.py",
            "--host", args.host, "--seconds", str(args.seconds),
            "--interval", str(args.interval), "--output", str(output),
            "--require-client-traffic", "--isolated-l3",
        ], args.seconds + 60, check=False)
        print(monitor.stdout, end="")
        if monitor.stderr:
            print(monitor.stderr, file=sys.stderr, end="")
        if monitor.returncode != 0:
            raise RuntimeError(f"5 GHz client gate failed rc={monitor.returncode}")
        commit(args.host, args.run_id)
    except Exception:
        if overlay_staged:
            failure_log = output.with_suffix(output.suffix + ".failure.txt")
            collect_radio5_failure_snapshot(args.host, failure_log, args.run_id)
            print(f"OMW3TX7_FAILURE_SNAPSHOT_LOCAL={failure_log}", file=sys.stderr)
            stop_radio5(args.host, "tx7-client-gate-failed")
            cleanup_safe_overlay(args.host)
        raise
    print(
        "W3_TX7_5G_CLIENT_TRAFFIC_PASS=1 association=1 bidirectional=1 "
        "irq8=progress irq20=progress eth0=preserved radio2g=preserved flash=0 "
        f"evidence={output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
