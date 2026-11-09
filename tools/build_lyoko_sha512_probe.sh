#!/bin/sh
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
arc_src=${LYOKO_DROPBEAR_ARC:-/home/user/openmitrastar-ssh-lab/dropbear-arc}
native_src=${LYOKO_DROPBEAR_NATIVE:-/home/user/openmitrastar-ssh-lab/dropbear-native}
sysroot=${LYOKO_ARC_SYSROOT:-/home/user/openmitrastar-uclibc-noatomic-sysroot}
tc="$root/work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-linux-"
src="$root/tools/lyoko_sha512_probe.c"
out="$root/outputs/packages/lyoko-sha512-probe"
mkdir -p "$out"

gcc -Os -I"$native_src" -I"$native_src/src" -I"$native_src/libtomcrypt/src/headers" "$src" \
  "$native_src/libtomcrypt/libtomcrypt.a" -o "$out/lyoko-sha512-probe-native"
"${tc}gcc" --sysroot="$sysroot" -Os -static -I"$arc_src" -I"$arc_src/src" -I"$arc_src/libtomcrypt/src/headers" "$src" \
  "$arc_src/libtomcrypt/libtomcrypt.a" -o "$out/lyoko-sha512-probe-arc"
"${tc}gcc" --sysroot="$sysroot" -Os -DENDIAN_NEUTRAL -DLTC_NO_ASM \
  -I"$arc_src" -I"$arc_src/src" -I"$arc_src/libtomcrypt/src/headers" \
  -c "$arc_src/libtomcrypt/src/hashes/sha2/sha512.c" -o "$out/sha512-neutral.o"
"${tc}gcc" --sysroot="$sysroot" -Os -static -I"$arc_src" -I"$arc_src/src" \
  -I"$arc_src/libtomcrypt/src/headers" "$src" "$out/sha512-neutral.o" \
  "$arc_src/libtomcrypt/libtomcrypt.a" -o "$out/lyoko-sha512-probe-arc-neutral"
"${tc}gcc" --sysroot="$sysroot" -O0 -fno-strict-aliasing -fwrapv -DENDIAN_NEUTRAL -DLTC_NO_ASM \
  -I"$arc_src" -I"$arc_src/src" -I"$arc_src/libtomcrypt/src/headers" \
  -c "$arc_src/libtomcrypt/src/hashes/sha2/sha512.c" -o "$out/sha512-neutral-o0.o"
"${tc}gcc" --sysroot="$sysroot" -O0 -fno-strict-aliasing -fwrapv -static \
  -I"$arc_src" -I"$arc_src/src" -I"$arc_src/libtomcrypt/src/headers" "$src" \
  "$out/sha512-neutral-o0.o" "$arc_src/libtomcrypt/libtomcrypt.a" \
  -o "$out/lyoko-sha512-probe-arc-neutral-o0"

assets="$root/outputs/packages/lyoko-runtime-signature"
packages="$root/outputs/packages/lyoko-v1/repository/Packages"
native=$($out/lyoko-sha512-probe-native "$assets/Packages.sig" "$assets/lyoko-feed-ed25519.raw" "$packages")
python=$(python3 - "$assets/Packages.sig" "$assets/lyoko-feed-ed25519.raw" "$packages" <<'PY'
import hashlib, pathlib, sys
s = pathlib.Path(sys.argv[1]).read_bytes()[:32]
p = pathlib.Path(sys.argv[2]).read_bytes()
m = pathlib.Path(sys.argv[3]).read_bytes()
print(hashlib.sha512(s + p + m).hexdigest())
PY
)
[ "$native" = "$python" ]
"${tc}readelf" -h "$out/lyoko-sha512-probe-arc" | grep -q 'ARC700, v4 ABI'
"${tc}readelf" -h "$out/lyoko-sha512-probe-arc-neutral" | grep -q 'ARC700, v4 ABI'
"${tc}readelf" -h "$out/lyoko-sha512-probe-arc-neutral-o0" | grep -q 'ARC700, v4 ABI'
sha256sum "$out/lyoko-sha512-probe-native" "$out/lyoko-sha512-probe-arc" \
  "$out/lyoko-sha512-probe-arc-neutral" "$out/lyoko-sha512-probe-arc-neutral-o0" > "$out/SHA256SUMS"
printf 'LYOKO_SHA512_PROBE_BUILD_PASS digest=%s\n' "$native"
