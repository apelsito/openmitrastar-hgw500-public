#!/bin/sh
set -eu

workspace=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
rootfs="$workspace/work/mission-state/q2-integrated-lzma-candidate/rootfs-build/openmitrastar-q2-parity-rootfs-v1.squashfs"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT INT TERM

[ -f "$rootfs" ]
unsquashfs -no-progress -d "$tmp/root" "$rootfs" >/dev/null

sha() { sha256sum "$1" | awk '{print $1}'; }
[ "$(sha "$tmp/root/usr/sbin/mini_httpd-tls")" = 2a366556ee9ff59b590efc685fcfd5232e64845f2a3ce84244ec4b42b0433d9f ]
[ "$(sha "$tmp/root/usr/sbin/om-config-backup")" = a2c60f05df54190285a0eb9b28b2732497ed598856491689203a956aa015c7a3 ]
[ "$(sha "$tmp/root/usr/sbin/om-config-restore")" = 9085e95ee7d8d0060f32f9826472e337534d2e7070b8d98b2772ce8a8f571a36 ]
[ "$(sha "$tmp/root/etc/init.d/S44-oem-web")" = 9980e627f2f0322ab3133139f121de759b05d451ea8f84b2fc9eb5a0d7599ee2 ]
[ "$(sha "$tmp/root/etc/minihttpd-https.conf")" = daf9c3ea0765e35d45aa532da18c1fe171bc6135f1126c714672c061bf2f1230 ]
[ "$(sha "$tmp/root/etc/minihttpd-getinfo.conf")" = 70b38549541d55ad2b4f77cccd03f6c7aa29a2b8ebd77f38f2a831c363441e00 ]

switch="$tmp/root/usr/libexec/openmitrastar/w3-no-ioss/switch-emac-handoff"
contract="$tmp/root/usr/share/openmitrastar/q2-w3-no-ioss.json"
normalization="$tmp/root/usr/share/openmitrastar/q2-w4-pin-normalization.json"
[ -f "$switch" ] && [ -f "$contract" ] && [ -f "$normalization" ]
guard=$(grep -n 'q2_ioss_reset_forbidden' "$switch" | cut -d: -f1)
first=$(grep -n 'load_module qtn_pm_qos_compat.ko' "$switch" | cut -d: -f1)
[ "$guard" -lt "$first" ]

python3 - "$contract" "$normalization" <<'PY'
import json, sys
contract = json.load(open(sys.argv[1], encoding="utf-8"))
pins = json.load(open(sys.argv[2], encoding="utf-8"))
assert contract["schema"] == "openmitrastar.q2-w3-no-ioss/v1"
assert contract["ioss_reset_pulse"] == "forbidden-by-q2-guard"
assert contract["required_gate"] == "W3_SKIP_IOSS_RESET_PULSE=1"
assert contract["autostart"] is False and contract["rf_default"] == "blocked"
assert contract["flash_write"] is False and contract["hardware_validation"] == "pending"
assert pins["unrecognized_hash_mismatches"] == []
assert pins["hash_corrections"] == [{
    "path": "etc/init.d/S44-oem-web",
    "w4_declared_sha256": "77576fd2d851c803f13a06ae91e2c2c2422a894d50ab6f8aed86cbccaa751cb9",
    "q2_canonical_sha256": "9980e627f2f0322ab3133139f121de759b05d451ea8f84b2fc9eb5a0d7599ee2",
    "reason": "mini_httpd-pidfile-fork-race-live-3x-restart-pass",
}]
assert pins["size_corrections"] == [
    {
        "path": "etc/init.d/S44-oem-web",
        "w4_declared_size": 3314,
        "q2_observed_size": 3601,
        "sha256": "9980e627f2f0322ab3133139f121de759b05d451ea8f84b2fc9eb5a0d7599ee2",
    },
    {
        "path": "etc/minihttpd-https.conf",
        "w4_declared_size": 331,
        "q2_observed_size": 284,
        "sha256": "daf9c3ea0765e35d45aa532da18c1fe171bc6135f1126c714672c061bf2f1230",
    },
]
PY

for path in \
	"$tmp/root/lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio2g/rtl8192ee.ko" \
	"$tmp/root/lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio5g/qdrv.ko" \
	"$tmp/root/www/getinfo.cgi" "$tmp/root/www-getinfo/cpe"; do
	[ -f "$path" ] || { echo "missing Q2 rootfs payload: $path" >&2; exit 1; }
done

! find "$tmp/root" -type f \( -name '*.pem' -o -name '*.key' -o -name '*.p12' -o -name '*.pfx' \) | grep -q .
! grep -R -a -E -l 'BEGIN (RSA |EC )?PRIVATE KEY|OM_PRODUCT_PRIVATE_PSK|wpa_passphrase=' "$tmp/root" >/dev/null 2>&1

printf 'OMQ2_ROOTFS_CONTRACT_PASS rootfs_sha256=%s backup_restore=1 https=443 getinfo=16667 w3_no_ioss=1 secrets=0\n' "$(sha "$rootfs")"
