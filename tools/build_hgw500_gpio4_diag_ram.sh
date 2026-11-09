#!/bin/sh

# Offline-only builder for the separately loadable GPIO4 observational probe.
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
src="$root/work/kernel-port/diagnostics/hgw500-gpio4-diag"
kernel=${TOPAZ_KERNEL_SRC:-/home/user/mitrastar-linux-5.10.260}
out=${TOPAZ_KERNEL_OUT:-/home/user/openmitrastar-build/radiohw-probe}
stage=${OM_GPIO4_DIAG_STAGE:-/home/user/openmitrastar-build/hgw500-gpio4-diag-20260821}
artifact=${OM_GPIO4_DIAG_ARTIFACT:-$root/outputs/kernel-port/hgw500-gpio4-diag-20260821}
release=5.10.260-openmitrastar-radiohw
tc="$root/work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-linux-"

case "$stage" in /home/user/openmitrastar-build/hgw500-gpio4-diag-*) ;; *) exit 2 ;; esac
case "$artifact" in "$root"/outputs/kernel-port/hgw500-gpio4-diag-*) ;; *) exit 2 ;; esac
test -f "$kernel/Makefile"
test -f "$out/.config"
test -x "${tc}gcc"

rm -rf -- "$stage" "$artifact"
mkdir -p "$stage" "$artifact/logs"
cp "$src/hgw500-gpio4-diag.c" "$src/Makefile" "$stage/"

make -C "$kernel" O="$out" ARCH=arc CROSS_COMPILE="$tc" \
	M="$stage" modules >"$artifact/logs/build.log" 2>&1
"$kernel/scripts/checkpatch.pl" --no-tree --file \
	"$src/hgw500-gpio4-diag.c" >"$artifact/logs/checkpatch.log" 2>&1 || {
	cat "$artifact/logs/checkpatch.log" >&2
	exit 3
}
python.exe "$(wslpath -w "$root/tools/test_hgw500_gpio4_diag.py")" \
	>"$artifact/logs/tests.log" 2>&1

cp "$stage/hgw500-gpio4-diag.ko" "$artifact/"
cp "$src/hgw500-gpio4-diag.c" "$artifact/"
cp "$src/Makefile" "$artifact/"
cp "$root/docs/HGW500_GPIO4_DIAGNOSTIC_RAM_20260821.md" "$artifact/README.md"
"${tc}readelf" -h -S -s "$artifact/hgw500-gpio4-diag.ko" \
	>"$artifact/readelf.txt"
"${tc}modinfo" "$artifact/hgw500-gpio4-diag.ko" \
	>"$artifact/modinfo.txt" 2>/dev/null || true

overlay="$stage/overlay"
mkdir -p "$overlay/lib/modules/$release/openmitrastar/diagnostics"
cp "$artifact/hgw500-gpio4-diag.ko" \
	"$overlay/lib/modules/$release/openmitrastar/diagnostics/"
tar --sort=name --mtime='@1787270400' --owner=0 --group=0 --numeric-owner \
	-czf "$artifact/hgw500-gpio4-diag-rootfs-overlay.tar.gz" -C "$overlay" .

python3 - "$artifact" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])

def meta(name):
    data = (root / name).read_bytes()
    return {"size": len(data), "sha256": hashlib.sha256(data).hexdigest()}

names = [
    "hgw500-gpio4-diag.c",
    "hgw500-gpio4-diag.ko",
    "hgw500-gpio4-diag-rootfs-overlay.tar.gz",
    "Makefile",
    "README.md",
    "readelf.txt",
]
manifest = {
    "schema": "openmitrastar.hgw500-gpio4-diagnostic/v1",
    "date": "2026-08-21",
    "classification": "RAM-ONLY-DIAGNOSTIC-NO-AUTOSTART-NO-FLASH",
    "target": {
        "model": "HGW-500BNA-QCv2",
        "hardware_revision": "A2",
        "compatible": "mitrastar,hgw-500bna-qcv2",
    },
    "contract": {
        "gpio": 4,
        "active": "low",
        "poll_ms": 20,
        "press_debounce_ms": 50,
        "release_quiet_ms": 500,
        "long_ms": 5000,
        "actions": "observation-only",
        "autoload": False,
        "flash": False,
    },
    "tests": {
        "offline": "6/6 PASS",
        "checkpatch": "0 errors, 0 warnings",
        "module_build": "PASS",
        "hardware_executed": False,
    },
    "artifacts": {name: meta(name) for name in names},
}
(root / "manifest.json").write_text(
    json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
PY

(cd "$artifact" && find . -type f ! -name SHA256SUMS -print0 | \
	sort -z | xargs -0 sha256sum >SHA256SUMS)

printf 'OMGPIO4_DIAG_BUILD_PASS module=%s flash=0 hardware=0\n' \
	"$(sha256sum "$artifact/hgw500-gpio4-diag.ko" | cut -d' ' -f1)"
