#!/bin/sh
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
version=1.4.85
sha256=18de51b393bac4a6827879e1a7ff377c169e414bae92cd245091d80fc2601d13
source_root=${LYOKO_LIGHTTPD_SOURCE:-/home/user/openmitrastar-build/lighttpd-$version-source}
meson_root=${LYOKO_MESON_SOURCE:-/home/user/openmitrastar-build/meson-1.8.3/src}
build_root=${LYOKO_LIGHTTPD_BUILD:-/home/user/openmitrastar-build/lighttpd-$version-arc700-minimal}
cross_file=${LYOKO_LIGHTTPD_CROSS_FILE:-$root/tools/lighttpd_arc700_cross.ini}
jobs=${LYOKO_JOBS:-12}

test -f "$source_root/lighttpd-$version.tar.xz"
test -f "$source_root/src/meson.build"
test -f "$meson_root/meson.py"
test -f "$cross_file"
echo "$sha256  $source_root/lighttpd-$version.tar.xz" | sha256sum -c -

rm -rf "$build_root"
python3 "$meson_root/meson.py" setup "$build_root" "$source_root/src" \
  --cross-file "$cross_file" \
  -Dbuild_static=true \
  -Dwith_pcre2=false \
  -Dwith_pcre=disabled \
  -Dwith_zlib=disabled \
  -Dwith_brotli=disabled \
  -Dwith_bzip=disabled \
  -Dwith_libdeflate=disabled \
  -Dwith_zstd=disabled \
  -Dwith_xxhash=disabled
ninja -C "$build_root" -j "$jobs" src/lighttpd

binary="$build_root/src/lighttpd"
test -x "$binary"
file "$binary"
sha256sum "$binary"
stat -c 'bytes=%s' "$binary"
readelf -h "$binary"
if readelf -l "$binary" | grep -q INTERP; then
  echo 'dynamic interpreter present' >&2
  exit 1
fi
if objdump -d "$binary" | grep -Eq '\b(llock|scond)\b'; then
  echo 'ARC atomic instruction present' >&2
  exit 1
fi
echo LIGHTTPD_ARC700_PROBE_PASS
