#!/bin/sh
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
source=/home/user/openmitrastar-ssh-lab/dropbear-arc
build=/home/user/openmitrastar-ssh-lab/dropbear-arc-radio
tc="$root/work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-linux-"
options="$root/work/ssh-emulation/dropbear-radio-localoptions.h"
root_only_patch="$root/work/ssh-emulation/dropbear-radio-root-only.patch"
artifacts="$root/outputs/kernel-port/dropbear-radio-multiuser"

test -x "$source/configure"
test -f "$options"
test -f "$root_only_patch"
test -x "${tc}gcc"
case "$build" in /home/user/openmitrastar-ssh-lab/*) ;; *) exit 3 ;; esac
case "$artifacts" in "$root"/outputs/*) ;; *) exit 3 ;; esac

incremental=${DROPBEAR_INCREMENTAL:-0}
case "$incremental" in 0|1) ;; *) exit 3 ;; esac
rm -rf -- "$artifacts"
mkdir -p "$artifacts"
if test "$incremental" = 0 || ! test -f "$build/Makefile"; then
	rm -rf -- "$build"
	cp -a "$source" "$build"
	cd "$build"
	make distclean >/dev/null 2>&1 || true
	cp "$options" "$build/localoptions.h"
	patch -p1 <"$root_only_patch"

	CC="${tc}gcc" AR="${tc}ar" RANLIB="${tc}ranlib" \
	STRIP="${tc}strip" ./configure \
		--host=arc-snps-linux-uclibc \
		--enable-static \
		--enable-bundled-libtom \
		--disable-zlib \
		--disable-syslog \
		--disable-shadow \
		--disable-lastlog \
		--disable-utmp \
		--disable-utmpx \
		--disable-wtmp \
		--disable-wtmpx \
		--disable-loginfunc >"$artifacts/configure.log" 2>&1
else
	cd "$build"
	cp "$options" "$build/localoptions.h"
	if ! grep -q 'DROPBEAR_OPENMITRASTAR_ROOT_ONLY' src/svr-auth.c; then
		patch -p1 <"$root_only_patch"
	fi
	printf 'incremental configured tree reuse\n' >"$artifacts/configure.log"
fi

make -j4 PROGRAMS=dropbear MULTI=1 STATIC=1 \
	>"$artifacts/build.log" 2>&1
test -x "$build/dropbearmulti"
"${tc}strip" "$build/dropbearmulti"
"${tc}readelf" -h "$build/dropbearmulti" | grep -Eq 'Class:.*ELF32'
"${tc}readelf" -h "$build/dropbearmulti" | grep -Eq 'Machine:.*(ARC|ARCompact)'
"${tc}readelf" -d "$build/dropbearmulti" | grep -q 'There is no dynamic section'
if strings "$build/dropbearmulti" | \
	grep -q 'Non-multiuser Dropbear requires a non-multiuser kernel'; then
	echo 'Dropbear radio build is still single-user' >&2
	exit 4
fi

cp "$build/dropbearmulti" "$artifacts/dropbearmulti"
sha256sum "$artifacts/dropbearmulti" >"$artifacts/SHA256SUMS"
printf 'DROPBEAR_RADIO_MULTIUSER_BUILD_PASS\n'
