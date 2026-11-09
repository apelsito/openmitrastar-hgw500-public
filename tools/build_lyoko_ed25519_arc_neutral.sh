#!/bin/sh
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
arc_src=${LYOKO_DROPBEAR_ARC:-/home/user/openmitrastar-ssh-lab/dropbear-arc}
sysroot=${LYOKO_ARC_SYSROOT:-/home/user/openmitrastar-uclibc-noatomic-sysroot}
tc="$root/work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-linux-"
build="$root/work/build/lyoko-ed25519-neutral"
out="$root/outputs/packages/lyoko-ed25519-neutral"
mkdir -p "$build" "$out"

common="--sysroot=$sysroot -Os -ffunction-sections -fdata-sections -I$arc_src -I$arc_src/src -I$arc_src/libtomcrypt/src/headers -I$arc_src/libtommath"
"${tc}gcc" $common -c "$root/tools/lyoko_ed25519_verify.c" -o "$build/main.o"
"${tc}gcc" $common -c "$arc_src/src/curve25519.c" -o "$build/curve25519.o"
"${tc}gcc" $common -DENDIAN_NEUTRAL -DLTC_NO_ASM \
  -c "$arc_src/libtomcrypt/src/hashes/sha2/sha512.c" -o "$build/sha512-neutral.o"
"${tc}gcc" --sysroot="$sysroot" -static -Wl,--gc-sections \
  "$build/main.o" "$build/curve25519.o" "$build/sha512-neutral.o" \
  "$arc_src/libtomcrypt/libtomcrypt.a" "$arc_src/libtommath/libtommath.a" \
  -o "$out/lyoko-ed25519-verify-arc-neutral"

common_o0="--sysroot=$sysroot -O0 -fno-strict-aliasing -fwrapv -ffunction-sections -fdata-sections -I$arc_src -I$arc_src/src -I$arc_src/libtomcrypt/src/headers -I$arc_src/libtommath"
"${tc}gcc" $common_o0 -c "$root/tools/lyoko_ed25519_verify.c" -o "$build/main-o0.o"
"${tc}gcc" $common_o0 -c "$arc_src/src/curve25519.c" -o "$build/curve25519-o0.o"
"${tc}gcc" $common_o0 -DENDIAN_NEUTRAL -DLTC_NO_ASM \
  -c "$arc_src/libtomcrypt/src/hashes/sha2/sha512.c" -o "$build/sha512-neutral-o0.o"
"${tc}gcc" --sysroot="$sysroot" -static -Wl,--gc-sections \
  "$build/main-o0.o" "$build/curve25519-o0.o" "$build/sha512-neutral-o0.o" \
  "$arc_src/libtomcrypt/libtomcrypt.a" "$arc_src/libtommath/libtommath.a" \
  -o "$out/lyoko-ed25519-verify-arc-neutral-o0"

"${tc}readelf" -h "$out/lyoko-ed25519-verify-arc-neutral" | grep -q 'ARC700, v4 ABI'
"${tc}readelf" -h "$out/lyoko-ed25519-verify-arc-neutral-o0" | grep -q 'ARC700, v4 ABI'
if "${tc}objdump" -d "$out/lyoko-ed25519-verify-arc-neutral" | grep -Eq '\b(llock|scond)\b'; then
  echo 'unsupported ARC atomic instruction found' >&2
  exit 1
fi
sha256sum "$out/lyoko-ed25519-verify-arc-neutral" \
  "$out/lyoko-ed25519-verify-arc-neutral-o0" > "$out/SHA256SUMS"
printf 'LYOKO_ED25519_NEUTRAL_BUILD_PASS sha256='
sha256sum "$out/lyoko-ed25519-verify-arc-neutral" | cut -d' ' -f1
