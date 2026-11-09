#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
sysroot=${LYOKO_ARC_SYSROOT:-/home/user/openmitrastar-uclibc-noatomic-sysroot}
tc="$root/work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-linux-"
out="$root/outputs/packages/lyoko-sha512-32"
mkdir -p "$out"
gcc -O2 -I"$root/tools" "$root/tools/lyoko_sha512_32.c" "$root/tools/lyoko_sha512_32_probe.c" -o "$out/probe-native"
"${tc}gcc" --sysroot="$sysroot" -O2 -static -I"$root/tools" \
  "$root/tools/lyoko_sha512_32.c" "$root/tools/lyoko_sha512_32_probe.c" -o "$out/probe-arc"
gcc -O2 -I"$root/tools" "$root/tools/lyoko_sha512_32.c" \
  "$root/tools/lyoko_sha512_32_selftest.c" -o "$out/selftest-native"
"${tc}gcc" --sysroot="$sysroot" -O2 -static -I"$root/tools" \
  "$root/tools/lyoko_sha512_32.c" "$root/tools/lyoko_sha512_32_selftest.c" -o "$out/selftest-arc"
assets="$root/outputs/packages/lyoko-runtime-signature"
packages="$root/outputs/packages/lyoko-v1/repository/Packages"
digest=$($out/probe-native "$assets/Packages.sig" "$assets/lyoko-feed-ed25519.raw" "$packages")
expected=$(python3 - "$assets/Packages.sig" "$assets/lyoko-feed-ed25519.raw" "$packages" <<'PY'
import hashlib, pathlib, sys
print(hashlib.sha512(pathlib.Path(sys.argv[1]).read_bytes()[:32] + pathlib.Path(sys.argv[2]).read_bytes() + pathlib.Path(sys.argv[3]).read_bytes()).hexdigest())
PY
)
[ "$digest" = "$expected" ]
selftest=$($out/selftest-native)
printf '%s\n' "$selftest" > "$out/selftest.expected"
grep -qx 'abc=ddaf35a193617abacc417349ae20413112e6fa4e89a97ea20a9eeee64b55d39a2192992a274fc1a836ba3c23a3feebbd454d4423643ce80e2a9ac94fa54ca49f' "$out/selftest.expected"
"${tc}readelf" -h "$out/probe-arc" | grep -q 'ARC700, v4 ABI'
sha256sum "$out/probe-native" "$out/probe-arc" "$out/selftest-native" "$out/selftest-arc" "$out/selftest.expected" > "$out/SHA256SUMS"
printf 'LYOKO_SHA512_32_BUILD_PASS digest=%s\n' "$digest"
