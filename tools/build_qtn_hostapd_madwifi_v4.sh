#!/bin/sh
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
source=$root/work/sources/Quantenna-GPL/buildroot/package/zhostapd/hostapd-git
config=$root/work/mission-state/w3-offline/hostapd-qtn-madwifi-v4.config
build=${QTN_HOSTAPD_BUILD:-/home/user/openmitrastar-build/hostapd-qtn-madwifi-v4}
out=${QTN_HOSTAPD_ARTIFACTS:-$root/outputs/kernel-port/qtn-hostapd-madwifi-v4-20260820}
sysroot=${ARC_NOATOMIC_SYSROOT:-/home/user/openmitrastar-uclibc-noatomic-sysroot}
tc=$root/work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-linux-
qtn_headers=$root/work/sources/Quantenna-GPL/drivers/include/shared
madwifi_headers=$root/work/sources/Quantenna-GPL/buildroot/package/zhostapd/madwifi
jobs=${TOPAZ_JOBS:-12}

for required in "$source/hostapd/Makefile" "$source/src/drivers/driver_madwifi.c" \
	"$config" "$sysroot/usr/include" "${tc}gcc" "$qtn_headers/net80211/ieee80211_ioctl.h" \
	"$madwifi_headers/include/compat.h"; do
	[ -e "$required" ] || { echo "missing input: $required" >&2; exit 3; }
done
rm -rf "$build" "$out"
mkdir -p "$build" "$out"
cp -a "$source"/. "$build"/
cp "$config" "$build/hostapd/.config"
# GCC 15 treats the OEM parameter name `bool` as the stdbool macro/type.
# Rename only that local parameter in the isolated build copy.
sed -i 's/bool_txt(Boolean bool)/bool_txt(Boolean value)/' \
	"$build/src/ap/ieee802_1x.c"
sed -i 's/return bool ? "TRUE" : "FALSE";/return value ? "TRUE" : "FALSE";/' \
	"$build/src/ap/ieee802_1x.c"
sed -i 's/wpa_bool_txt(int bool)/wpa_bool_txt(int value)/' \
	"$build/src/ap/wpa_auth.c"
sed -i 's/return bool ? "TRUE" : "FALSE";/return value ? "TRUE" : "FALSE";/' \
	"$build/src/ap/wpa_auth.c"
python3 - "$build/src/utils/os_unix.c" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text()
old = '''void os_sleep(os_time_t sec, os_time_t usec)
{
\tif (sec)
\t\tsleep(sec);
\tif (usec)
\t\tusleep(usec);
}
'''
new = '''void os_sleep(os_time_t sec, os_time_t usec)
{
\tstruct timespec req;
\treq.tv_sec = sec + usec / 1000000;
\treq.tv_nsec = (usec % 1000000) * 1000;
\twhile (nanosleep(&req, &req) < 0 && errno == EINTR)
\t\t;
}
'''
if old not in text:
    raise SystemExit("os_sleep source contract changed")
path.write_text(text.replace(old, new))
PY
{
	printf '\nCFLAGS += --sysroot=%s -Os -g0 -mno-atomic -fno-stack-protector -ffunction-sections -fdata-sections\n' "$sysroot"
	printf 'CFLAGS += -I%s -I%s -D_GNU_SOURCE\n' "$qtn_headers" "$madwifi_headers"
	printf 'LDFLAGS += --sysroot=%s -static -Wl,--gc-sections\n' "$sysroot"
} >>"$build/hostapd/.config"
make -C "$build/hostapd" clean >/dev/null 2>&1 || true
make -C "$build/hostapd" -j"$jobs" hostapd hostapd_cli \
	CC="${tc}gcc" AR="${tc}ar" PKG_CONFIG=/bin/false V=1
"${tc}strip" --strip-unneeded "$build/hostapd/hostapd" "$build/hostapd/hostapd_cli"
for binary in hostapd hostapd_cli; do
	file=$build/hostapd/$binary
	"${tc}readelf" -h "$file" | grep -Eq 'Machine:.*ARC|Machine:.*ARCompact'
	"${tc}readelf" -h "$file" | grep -q 'Flags:.*0x403'
	! "${tc}readelf" -l "$file" | grep -q 'Requesting program interpreter'
	! "${tc}objdump" -d "$file" | grep -Eq '\b(llock|scond)\b'
	cp "$file" "$out/$binary"
done
cp "$config" "$out/hostapd-qtn-madwifi-v4.config"
sha256sum "$out/hostapd" "$out/hostapd_cli" "$out/hostapd-qtn-madwifi-v4.config" >"$out/SHA256SUMS"
grep -a -q 'madwifi' "$out/hostapd"
printf 'QTN_HOSTAPD_MADWIFI_V4_BUILD_PASS=1 hostapd_sha256='
sha256sum "$out/hostapd" | cut -d' ' -f1
