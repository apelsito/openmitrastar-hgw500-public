#!/bin/sh

set -eu

workspace=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
project="$workspace/work/mission-state/w4-rootfs-product"
source_file="$project/src/om_product_entropy_seed.c"
fragment="$project/kernel/topaz-product-rootfs.fragment"
kernel_src=${TOPAZ_KERNEL_SRC:-/home/user/mitrastar-linux-5.10.260}
base_config=${OM_ENTROPY_BASE_CONFIG:-/home/user/openmitrastar-build/q1-full-product/kernel/kernel-a/.config}
build_root=${OM_ENTROPY_BUILD_ROOT:-/home/user/openmitrastar-build/autonomous-entropy-gate}
artifact=${OM_ENTROPY_ARTIFACT_DIR:-$workspace/outputs/kernel-port/autonomous-entropy-gate-20260820}
tc="$workspace/work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-linux-"
sysroot=${OM_NOATOMIC_SYSROOT:-/home/user/openmitrastar-uclibc-noatomic-sysroot}
epoch=${SOURCE_DATE_EPOCH:-1787011200}

case "$build_root" in /home/user/openmitrastar-build/*) ;; *) exit 2 ;; esac
case "$artifact" in "$workspace"/outputs/kernel-port/*) ;; *) exit 2 ;; esac
for required in "$source_file" "$fragment" "$kernel_src/Makefile" \
	"$kernel_src/scripts/config" "$base_config" "${tc}gcc" "${tc}readelf" \
	"${tc}objdump" "$project/scripts/test_product_rootfs.py"; do
	[ -e "$required" ] || { echo "missing entropy build input: $required" >&2; exit 3; }
done
[ -d "$sysroot" ] || { echo "missing no-atomic sysroot: $sysroot" >&2; exit 3; }

rm -rf -- "$build_root" "$artifact"
mkdir -p "$build_root/host-test" "$build_root/kernel" "$artifact/evidence"
log="$artifact/evidence/validation.log"
exec >"$log" 2>&1

python3 - "$project/scripts/test_product_rootfs.py" "$source_file" "$build_root/host-test" <<'PY'
import importlib.util
import pathlib
import sys

test_path, source_path, work_path = map(pathlib.Path, sys.argv[1:])
spec = importlib.util.spec_from_file_location("om_product_tests", test_path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.exercise_entropy_helper(source_path, work_path)
print("OM_ENTROPY_HOST_TEST_PASS cases=success,short-source,crng-not-ready")
PY

export SOURCE_DATE_EPOCH=$epoch
common_flags="--sysroot=$sysroot -mno-atomic -fno-stack-protector -std=c99 -Os -static -s -Wall -Wextra -Werror -ffile-prefix-map=$project=/usr/src/openmitrastar-product"
"${tc}gcc" $common_flags -o "$build_root/om-entropy-seed-a" "$source_file"
"${tc}gcc" $common_flags -o "$build_root/om-entropy-seed-b" "$source_file"
cmp -s "$build_root/om-entropy-seed-a" "$build_root/om-entropy-seed-b"
"${tc}readelf" -h "$build_root/om-entropy-seed-a" | grep -q 'ARC700, v4 ABI'
! "${tc}readelf" -l "$build_root/om-entropy-seed-a" | grep -q INTERP
! "${tc}objdump" -d "$build_root/om-entropy-seed-a" | \
	grep -Eq '[[:space:]](llock|scond)([.[:space:]]|$)'
! strings "$build_root/om-entropy-seed-a" | grep -q '/dev/ttyS0'
! strings "$build_root/om-entropy-seed-a" | grep -q 'ENTROPY_SEED_REQUIRED'
strings "$build_root/om-entropy-seed-a" | grep -q 'jitterentropy_rng'
strings "$build_root/om-entropy-seed-a" | grep -q 'OMPRODUCT_ENTROPY_LOCAL_OK'
echo 'OM_ENTROPY_ARC_BUILD_PASS abi=ARC700-v4 static=1 atomics=0 reproducible=1'

cp "$base_config" "$build_root/kernel/.config"
while IFS= read -r line; do
	case "$line" in
	CONFIG_*=y)
		symbol=${line%%=*}
		"$kernel_src/scripts/config" --file "$build_root/kernel/.config" \
			--enable "${symbol#CONFIG_}"
		;;
	'# CONFIG_'*' is not set')
		symbol=${line#\# CONFIG_}
		symbol=${symbol% is not set}
		"$kernel_src/scripts/config" --file "$build_root/kernel/.config" \
			--disable "$symbol"
		;;
	esac
done <"$fragment"
make -s -C "$kernel_src" O="$build_root/kernel" ARCH=arc olddefconfig
grep -qx 'CONFIG_CRYPTO_JITTERENTROPY=y' "$build_root/kernel/.config"
grep -qx 'CONFIG_CRYPTO_USER_API=y' "$build_root/kernel/.config"
grep -qx 'CONFIG_CRYPTO_USER_API_RNG=y' "$build_root/kernel/.config"
make -s -C "$kernel_src" O="$build_root/kernel" ARCH=arc \
	CROSS_COMPILE="$tc" -j4 crypto/jitterentropy.o \
	crypto/jitterentropy-kcapi.o crypto/algif_rng.o
echo 'OM_ENTROPY_KCONFIG_PASS jitterentropy=builtin af_alg_rng=builtin'

python3 - <<'PY'
import socket

with open("/proc/crypto", encoding="ascii") as handle:
    crypto = handle.read()
assert "name         : jitterentropy_rng" in crypto
assert "selftest     : passed" in crypto
parent = socket.socket(socket.AF_ALG, socket.SOCK_SEQPACKET, 0)
parent.bind(("rng", "jitterentropy_rng"))
operation, _ = parent.accept()
first = operation.recv(32)
second = operation.recv(32)
assert len(first) == 32 and len(second) == 32 and first != second
operation.close()
parent.close()
print("OM_ENTROPY_AFALG_SMOKE_PASS source=jitterentropy_rng bytes=64 selftest=passed")
PY

cp "$build_root/om-entropy-seed-a" "$artifact/om-entropy-seed"
cp "$source_file" "$artifact/om_product_entropy_seed.c"
cp "$fragment" "$artifact/topaz-product-rootfs.fragment"
cp "$build_root/kernel/.config" "$artifact/evidence/kernel.config"
cp "$build_root/kernel/crypto/jitterentropy.o" "$artifact/evidence/jitterentropy.o"
cp "$build_root/kernel/crypto/jitterentropy-kcapi.o" "$artifact/evidence/jitterentropy-kcapi.o"
cp "$build_root/kernel/crypto/algif_rng.o" "$artifact/evidence/algif_rng.o"
cp "$project/rootfs/etc/init.d/S05-entropy" "$artifact/S05-entropy"
cp "$project/rootfs/etc/init.d/rcS" "$artifact/rcS"
cp "$project/rootfs/usr/sbin/om-ssh" "$artifact/om-ssh"

python3 - "$artifact" <<'PY'
import hashlib
import json
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
files = {}
for path in sorted(root.rglob("*")):
    if path.is_file() and path.name not in {"manifest.json", "SHA256SUMS", "validation.log"}:
        files[path.relative_to(root).as_posix()] = {
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "size": path.stat().st_size,
        }
manifest = {
    "schema": "openmitrastar.autonomous-entropy-gate/v1",
    "candidate_eligible": False,
    "scope": "Q3 integration input; offline only; no COM3 and no flash",
    "source": {
        "algorithm": "jitterentropy_rng",
        "interface": "AF_ALG rng",
        "health_tests": "kernel startup plus continuous RCT/APT",
        "credited_bits": 256,
        "constant_seed": False,
        "persistent_seed": False,
        "uart_dependency": False,
    },
    "fail_closed": {
        "crng_probe": "getrandom(GRND_NONBLOCK)",
        "ready_marker": "/run/openmitrastar/entropy.ready",
        "rcs_aborts_on_failure": True,
        "ssh_rechecks_marker": True,
    },
    "kernel_required": [
        "CONFIG_CRYPTO_JITTERENTROPY=y",
        "CONFIG_CRYPTO_USER_API_RNG=y",
    ],
    "files": files,
}
(root / "manifest.json").write_text(
    json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
PY
(cd "$artifact" && sha256sum $(find . -type f ! -name SHA256SUMS ! -name validation.log | LC_ALL=C sort) >SHA256SUMS)
echo "OM_ENTROPY_BUNDLE_PASS artifact=$artifact"
