from __future__ import annotations

from pathlib import Path
import shlex
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "versions/lyoko-foundation-6.3.7-f283-qtn-ssid-material-trial/overlay/usr/sbin/om-qtn-material-trial"


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


def test_material_trial_applies_fixed_ssid_then_restores() -> None:
    with tempfile.TemporaryDirectory(prefix="lyoko-f283-trial-") as directory:
        root = Path(directory)
        tmp = wsl_path(root)
        script = wsl_path(SCRIPT)
        command = f'''
set -eu
mkdir -p {tmp}/bin {tmp}/state
printf 'OPENMITRASTAR_QTN_NATIVE_CONTROL=1\n' > {tmp}/feature
printf 'MOVISTAR_PLUS_55CB\n' > {tmp}/ssid
printf '36\n' > {tmp}/channel
printf '80\n' > {tmp}/bandwidth
cat > {tmp}/bin/qtnctl <<'SH'
#!/bin/sh
root=${{OM_TEST_ROOT:?}}
case "$1:$2" in
get:ssid) cat "$root/ssid";;
get:channel) cat "$root/channel";;
get:bandwidth) cat "$root/bandwidth";;
apply:*)
  file=$2
  ssid=$(sed -n 's/^ssid=//p' "$file" | sed -n '1p')
  channel=$(sed -n 's/^channel=//p' "$file" | sed -n '1p')
  bandwidth=$(sed -n 's/^bandwidth=//p' "$file" | sed -n '1p')
  printf '%s\n' "$ssid" >> "$root/history"
  printf '%s\n' "$ssid" > "$root/ssid"
  printf '%s\n' "$channel" > "$root/channel"
  printf '%s\n' "$bandwidth" > "$root/bandwidth"
  printf '{{"ok":true,"applied":true,"verified":true}}\n'
  ;;
*) exit 2;;
esac
SH
chmod 755 {tmp}/bin/qtnctl
env OM_TEST_ROOT={tmp} OM_QTN_TRIAL_STATE={tmp}/state \
  OM_QTN_TRIAL_FEATURE={tmp}/feature OM_QTNCTL={tmp}/bin/qtnctl \
  OM_QTN_TRIAL_SELF={shlex.quote(script)} OM_QTN_TRIAL_HOLD_SECONDS=1 \
  OM_QTN_TRIAL_WATCHDOG_SECONDS=15 OM_QTN_TRIAL_ACK=OPENMITRASTAR_QTN_MATERIAL_TRIAL_V1 \
  sh {shlex.quote(script)} run
test "$(cat {tmp}/ssid)" = MOVISTAR_PLUS_55CB
test "$(sed -n '1p' {tmp}/history)" = Lyoko-5G-Material-Test
test "$(sed -n '2p' {tmp}/history)" = MOVISTAR_PLUS_55CB
test "$(wc -l < {tmp}/history)" = 2
test ! -e {tmp}/state/watchdog.armed
'''
        result = run_wsl(command)
        assert result.returncode == 0, result.stderr
        assert '"target_ssid":"Lyoko-5G-Material-Test"' in result.stdout
        assert '"restored_ssid":"MOVISTAR_PLUS_55CB"' in result.stdout


def test_material_trial_has_no_flash_or_secret_output_path() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert "OPENMITRASTAR_QTN_MATERIAL_TRIAL_V1" in source
    assert "watchdog.armed" in source
    assert "stage=restore-pass" in source
    assert "wpa_passphrase" not in source
    for forbidden in ("flash_erase", "mtd_debug", "spi_flash", "fw_setenv", "/dev/mtd", "/persist"):
        assert forbidden not in source

