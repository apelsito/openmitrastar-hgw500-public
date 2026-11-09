#!/usr/bin/env python3
"""Read-only inventory of user-configurable radio settings."""
from __future__ import annotations

import os

from deploy_openmitrastar_07_pty import ROOT, command, credentials, read_until
from winpty import PtyProcess


def main() -> int:
    user, password = credentials()
    ssh = os.path.join(os.environ["WINDIR"], "System32", "OpenSSH", "ssh.exe")
    argv = [
        ssh, "-tt", "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=NUL",
        "-o", "HostKeyAlgorithms=+ssh-rsa", "-o", "KexAlgorithms=+diffie-hellman-group1-sha1",
        "-o", "Ciphers=+aes128-cbc,3des-cbc", "-o", "MACs=+hmac-sha1,hmac-md5",
        f"{user}@192.168.1.90",
    ]
    proc = PtyProcess.spawn(argv, cwd=str(ROOT))
    read_until(proc, "password:", 20)
    proc.write(password + "\r\n")
    read_until(proc, "# ", 20)
    proc.write("stty -echo\r\n")
    read_until(proc, "# ", 10)
    probe = r'''
for item in \
  "mode|get_mode wifi0" \
  "ssid|get_SSID wifi0" \
  "channel|get_channel wifi0" \
  "bandwidth|get_bw wifi0" \
  "pmf|get_pmf wifi0" \
  "vht|get_vht wifi0" \
  "dtim|get_dtim wifi0" \
  "mcs|get_mcs_rate wifi0" \
  "scs|get_scs_status wifi0" \
  "beacon_type|get_beacon_type wifi0" \
  "ieee11i_auth|get_IEEE11i_authentication_mode wifi0" \
  "ieee11i_encryption|get_IEEE11i_encryption_modes wifi0" \
  "wps_state|get_wps_configured_state wifi0"
do
  label=${item%%|*}; args=${item#*|}
  value=$(/sbin/call_qcsapi $args 2>&1)
  rc=$?
  echo "$label|$rc|$value"
done
for option in short_GI WiFi_MultiMedia beamforming SSID_broadcast
do
  value=$(/sbin/call_qcsapi get_option wifi0 "$option" 2>&1)
  rc=$?
  echo "qopt:$option|$rc|$value"
done
for key in \
  enable.wlan1 ssid.wlan1 encryption.wlan1 channel.wlan1 bandwidth.wlan1 \
  wpsstate.wlan1 band.wlan1 coexist.wlan1 bcnint.wlan1 \
  dtimperiod.wlan1 shortgi.wlan1 fragthres.wlan1 rtsthres.wlan1 \
  preamble.wlan1 wmm.wlan1 extchannel.wlan1 wmm_apsd.wlan1 \
  stanum.wlan1 disable_protection.wlan1
do
  value=$(qweconfig get "$key" 2>&1); rc=$?; echo "qwe:$key|$rc|$value"
done
p5=$(/sbin/call_qcsapi get_key_passphrase wifi0 0 2>/dev/null)
if [ ${#p5} -ge 8 ]; then echo "passphrase5_set|0|yes"; else echo "passphrase5_set|0|no"; fi
unset p5
p24=$(qweconfig get passphrase.wlan1 2>/dev/null)
if [ ${#p24} -ge 8 ]; then echo "passphrase24_set|0|yes"; else echo "passphrase24_set|0|no"; fi
unset p24
'''.strip()
    output = command(proc, probe, "__RADIO_SETTINGS__", 90)
    print(output.strip())
    proc.write("exit\r\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
