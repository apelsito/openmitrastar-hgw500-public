from __future__ import annotations

from pathlib import Path
import shlex
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "versions/lyoko-foundation-6.3.6-f282-qtn-hostapd-restart-fix/overlay/usr/sbin/om-qtn-step"


def wsl_path(path: Path) -> str:
    resolved = path.resolve()
    return f"/mnt/{resolved.drive[0].lower()}/{resolved.as_posix()[3:]}"


def run_wsl(script: str, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["wsl.exe", "-d", "podman-mem9-tidb", "-u", "root", "-e", "sh", "-c", script],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )


def test_hostapd_restart_regenerates_config_and_kills_validated_pid() -> None:
    with tempfile.TemporaryDirectory(prefix="lyoko-f282-hostapd-") as directory:
        root = Path(directory)
        tmp = wsl_path(root)
        script = wsl_path(SCRIPT)
        setup = f'''
set -eu
mkdir -p {tmp}/bin {tmp}/state {tmp}/radio {tmp}/ctrl {tmp}/rtlctrl \
  {tmp}/sys/class/net/wifi0 {tmp}/sys/class/net/br0/brif/eth0 \
  {tmp}/sys/class/net/br0/brif/wlan0 {tmp}/sys/class/net/br0/brif/wifi0
printf 'OPENMITRASTAR_QTN_STEP_PROBE=1\n' > {tmp}/step-feature
printf 'OPENMITRASTAR_QTN_NATIVE_CONTROL=0\n' > {tmp}/qtn-feature
printf '1\n' > {tmp}/rf
printf 'OldSSID\n' > {tmp}/ssid
printf '36\n' > {tmp}/channel
printf '11ac80Edge+\n' > {tmp}/mode
printf 'abcdefgh\n' > {tmp}/psk
cat > {tmp}/bin/qtnctl <<'SH'
#!/bin/sh
root=${{OM_TEST_ROOT:?}}
[ "$1" = get ] && [ "$2" = channel ] && cat "$root/channel"
SH
cat > {tmp}/bin/iwconfig <<'SH'
#!/bin/sh
root=${{OM_TEST_ROOT:?}}
case "${{2:-}}" in
essid) printf '%s\n' "$3" > "$root/ssid";;
channel) printf '%s\n' "$3" > "$root/channel";;
*) printf 'wifi0 ESSID:"%s" Frequency:5.18 GHz Tx-Power=21 dBm\n' "$(cat "$root/ssid")";;
esac
SH
cat > {tmp}/bin/iwpriv <<'SH'
#!/bin/sh
root=${{OM_TEST_ROOT:?}}
case "${{2:-}}" in
get_mode) printf 'wifi0 get_mode:%s\n' "$(cat "$root/mode")";;
mode) printf '%s\n' "$3" > "$root/mode";;
init_txpower|doth|tpc) exit 0;;
*) exit 0;;
esac
SH
cat > {tmp}/bin/ifconfig <<'SH'
#!/bin/sh
exit 0
SH
cat > {tmp}/bin/hostapd-cli <<'SH'
#!/bin/sh
root=${{OM_TEST_ROOT:?}}
case "$5" in
terminate) touch "$root/terminate-called";;
ping) pid=$(cat "$root/radio/hostapd.pid" 2>/dev/null || true); kill -0 "$pid" 2>/dev/null && printf 'PONG\n';;
get_config) printf 'ssid=%s\n' "$(cat "$root/ssid")";;
*) exit 2;;
esac
SH
cat > {tmp}/bin/rtl-hostapd-cli <<'SH'
#!/bin/sh
printf 'state=ENABLED\n'
SH
cat > {tmp}/bin/hostapd-qtn <<'SH'
#!/bin/sh
exec sleep 600
SH
cat > {tmp}/bin/dmesg <<'SH'
#!/bin/sh
exit 0
SH
chmod 755 {tmp}/bin/*
{tmp}/bin/hostapd-qtn &
old=$!
printf '%s\n' "$old" > {tmp}/old.pid
cp {tmp}/old.pid {tmp}/radio/hostapd.pid
env OM_TEST_ROOT={tmp} OM_QTN_STEP_FEATURE={tmp}/step-feature \
  OM_QTN_CONTROL_FEATURE={tmp}/qtn-feature OM_QTN_STEP_STATE={tmp}/state \
  OM_RADIO5_STATE={tmp}/radio OM_SYS_ROOT={tmp}/sys OM_PROC_ROOT=/proc \
  OM_QTN_RF_PATH={tmp}/rf OM_QTN_INTERFACE=wifi0 OM_QTN_BRIDGE=br0 \
  OM_IFCONFIG={tmp}/bin/ifconfig OM_QTNCTL={tmp}/bin/qtnctl \
  OM_IWCONFIG_QTN={tmp}/bin/iwconfig OM_IWPRIV_QTN={tmp}/bin/iwpriv \
  OM_QTN_HOSTAPD={tmp}/bin/hostapd-qtn OM_QTN_HOSTAPD_COMM=sleep \
  OM_QTN_HOSTAPD_CLI={tmp}/bin/hostapd-cli OM_QTN_HOSTAPD_CTRL={tmp}/ctrl \
  OM_RADIO5_PSK_FILE={tmp}/psk OM_RTL_HOSTAPD_CLI={tmp}/bin/rtl-hostapd-cli \
  OM_RTL_HOSTAPD_CTRL={tmp}/rtlctrl OM_DMESG={tmp}/bin/dmesg \
  OM_QTN_STEP_ACK=OPENMITRASTAR_QTN_STEP_V1 sh {shlex.quote(script)} probe hostapd-restart-same
rc=$?
set +e
new=$(cat {tmp}/radio/hostapd.pid)
old_alive=0; kill -0 "$old" 2>/dev/null && old_alive=1
new_alive=0; kill -0 "$new" 2>/dev/null && new_alive=1
config_size=$(wc -c < {tmp}/radio/hostapd.conf 2>/dev/null || printf 0)
config_mode=$(stat -c %a {tmp}/radio/hostapd.conf 2>/dev/null || printf missing)
terminate_called=0; test -e {tmp}/terminate-called && terminate_called=1
printf 'OLD=%s NEW=%s OLD_ALIVE=%s NEW_ALIVE=%s CONFIG_SIZE=%s CONFIG_MODE=%s TERMINATE=%s\n' \
  "$old" "$new" "$old_alive" "$new_alive" "$config_size" "$config_mode" "$terminate_called"
kill "$new" 2>/dev/null || true
test "$rc" = 0 && test "$new" != "$old" && test "$old_alive" = 0 && \
  test "$new_alive" = 1 && test "$config_size" -gt 0 && \
  test "$terminate_called" = 1
'''
        result = run_wsl(setup)
        assert result.returncode == 0, result.stderr
        assert "OMQTNSTEP pass step=hostapd-restart-same" in result.stdout
        assert "OLD_ALIVE=0" in result.stdout
        assert "NEW_ALIVE=1" in result.stdout
        assert "TERMINATE=1" in result.stdout
        assert "abcdefgh" not in result.stdout
        assert 'chmod 0600 "$conf"' in SCRIPT.read_text(encoding="utf-8")
