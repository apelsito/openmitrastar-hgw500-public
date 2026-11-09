#!/bin/sh
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
arc_src=${LYOKO_DROPBEAR_ARC:-/home/user/openmitrastar-ssh-lab/dropbear-arc}
native_src=${LYOKO_DROPBEAR_NATIVE:-/home/user/openmitrastar-ssh-lab/dropbear-native}
sysroot=${LYOKO_ARC_SYSROOT:-/home/user/openmitrastar-uclibc-noatomic-sysroot}
tc="$root/work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-linux-"
source_c="$root/tools/lyoko_ed25519_verify.c"
assets="$root/outputs/packages/lyoko-runtime-signature"
out="$root/outputs/packages/lyoko-ed25519-verify"
build="$root/work/build/lyoko-ed25519-verify"

test -f "$source_c"
test -s "$assets/lyoko-feed-ed25519.raw"
test -s "$assets/Packages.sig"
test -s "$root/outputs/packages/lyoko-v1/repository/Packages"
test -x "${tc}gcc"
mkdir -p "$out" "$build/native" "$build/arc"

common='-Os -ffunction-sections -fdata-sections'

compile_one()
{
	name=$1; cc=$2; src=$3; sysroot_flag=$4
	dir="$build/$name"
	$cc $sysroot_flag $common -I"$src" -I"$src/src" -I"$src/libtomcrypt/src/headers" -I"$src/libtommath" -c "$source_c" -o "$dir/main.o"
	$cc $sysroot_flag $common -I"$src" -I"$src/src" -I"$src/libtomcrypt/src/headers" -I"$src/libtommath" -c "$src/src/curve25519.c" -o "$dir/curve25519.o"
}

compile_one native gcc "$native_src" ''
gcc -Wl,--gc-sections "$build/native/main.o" "$build/native/curve25519.o" "$native_src/libtomcrypt/libtomcrypt.a" "$native_src/libtommath/libtommath.a" -o "$out/lyoko-ed25519-verify-native"
compile_one arc "${tc}gcc" "$arc_src" "--sysroot=$sysroot"
"${tc}gcc" --sysroot="$sysroot" -static -Wl,--gc-sections "$build/arc/main.o" "$build/arc/curve25519.o" "$arc_src/libtomcrypt/libtomcrypt.a" "$arc_src/libtommath/libtommath.a" -o "$out/lyoko-ed25519-verify-arc"

packages="$root/outputs/packages/lyoko-v1/repository/Packages"
"$out/lyoko-ed25519-verify-native" "$assets/lyoko-feed-ed25519.raw" "$assets/Packages.sig" "$packages"
cp "$packages" "$build/tampered-Packages"
printf '\n' >>"$build/tampered-Packages"
if "$out/lyoko-ed25519-verify-native" "$assets/lyoko-feed-ed25519.raw" "$assets/Packages.sig" "$build/tampered-Packages"; then
	echo 'tampered message was accepted' >&2
	exit 1
fi
cp "$assets/Packages.sig" "$build/tampered.sig"
printf '\001' | dd of="$build/tampered.sig" bs=1 seek=0 conv=notrunc status=none
if "$out/lyoko-ed25519-verify-native" "$assets/lyoko-feed-ed25519.raw" "$build/tampered.sig" "$packages"; then
	echo 'tampered signature was accepted' >&2
	exit 1
fi

"${tc}readelf" -h "$out/lyoko-ed25519-verify-arc" | grep -q 'ARC700, v4 ABI'
if "${tc}objdump" -d "$out/lyoko-ed25519-verify-arc" | grep -Eq '\b(llock|scond)\b'; then
	echo 'unsupported ARC atomic instruction found' >&2
	exit 1
fi
test "$(wc -c <"$out/lyoko-ed25519-verify-arc")" -le 131072

sha256sum "$out/lyoko-ed25519-verify-native" "$out/lyoko-ed25519-verify-arc" >"$out/SHA256SUMS"
cat >"$out/manifest.json" <<EOF
{
  "schema": "lyoko.ed25519-runtime-verifier/v1",
  "source": "Dropbear 2026.94 curve25519.c",
  "license": "MIT-style Dropbear notice plus public-domain TweetNaCl-derived implementation",
  "native_valid_signature": "PASS",
  "native_tampered_message": "REJECTED",
  "native_tampered_signature": "REJECTED",
  "arc_architecture": "ARC700 v4 ABI",
  "arc_bytes": $(wc -c <"$out/lyoko-ed25519-verify-arc"),
  "arc_sha256": "$(sha256sum "$out/lyoko-ed25519-verify-arc" | cut -d' ' -f1)",
  "arc_atomic_instructions": false,
  "arc_hardware_execution": "NOT_RUN",
  "hardware_actions": {"router": false, "uart": false, "flash": false}
}
EOF
echo 'LYOKO_ED25519_VERIFIER_BUILD_PASS=1'
