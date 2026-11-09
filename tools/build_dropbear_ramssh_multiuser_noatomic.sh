#!/bin/sh
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
source=/home/user/openmitrastar-ssh-lab/dropbear-arc
build=/home/user/openmitrastar-ssh-lab/dropbear-arc-multiuser-noatomic
tc="$root/work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-linux-"
sysroot=/home/user/openmitrastar-uclibc-noatomic-sysroot
options="$root/work/ssh-emulation/dropbear-ramssh-multiuser-noatomic-localoptions.h"
root_only_patch="$root/work/ssh-emulation/dropbear-radio-root-only.patch"
artifacts="$root/outputs/kernel-port/dropbear-ramssh-multiuser-noatomic"

test -x "$source/configure"
test -d "$sysroot"
test -f "$options"
test -f "$root_only_patch"
test -x "${tc}gcc"
case "$build" in /home/user/openmitrastar-ssh-lab/*) ;; *) exit 3 ;; esac

rm -rf -- "$build" "$artifacts"
mkdir -p "$artifacts"
cp -a "$source" "$build"
cd "$build"
cp "$options" localoptions.h
if ! grep -q 'DROPBEAR_OPENMITRASTAR_ROOT_ONLY' src/svr-auth.c; then
	patch -p1 <"$root_only_patch"
fi

# The source tree is already configured against the validated no-atomic
# sysroot.  Reusing it avoids several minutes of cross-compile feature probes.
grep -q -- '--sysroot=/home/user/openmitrastar-uclibc-noatomic-sysroot' Makefile
grep -q -- '-mno-atomic' Makefile
printf 'reused configured no-atomic tree\n' >"$artifacts/configure.log"
make clean >/dev/null 2>&1 || true

make -j"${DROPBEAR_JOBS:-8}" PROGRAMS="dropbear dropbearkey" MULTI=1 STATIC=1 \
	>"$artifacts/build.log" 2>&1
test -x dropbearmulti
"${tc}strip" dropbearmulti
"${tc}readelf" -h dropbearmulti | grep -q 'ARC700, v4 ABI'
"${tc}readelf" -d dropbearmulti | grep -q 'There is no dynamic section'
if "${tc}objdump" -d dropbearmulti | \
	grep -Eq '[[:space:]](llock|scond)([[:space:].]|$)'; then
	echo 'unsupported ARC atomic instruction in multiuser Dropbear' >&2
	exit 4
fi
if strings dropbearmulti | \
	grep -q 'Non-multiuser Dropbear requires a non-multiuser kernel'; then
	echo 'multiuser guard still present in Dropbear binary' >&2
	exit 5
fi
for applet in "'dropbear' - the Dropbear server" \
	"'dropbearkey' or 'ssh-keygen' - the key generator"; do
	strings dropbearmulti | grep -Fq "$applet" || {
		echo "missing Dropbear multi applet: $applet" >&2
		exit 6
	}
done
mkdir -p "$artifacts"
cp dropbearmulti "$artifacts/dropbearmulti"
sha256sum "$artifacts/dropbearmulti" >"$artifacts/SHA256SUMS"
printf 'DROPBEAR_RAMSSH_MULTIUSER_NOATOMIC_PASS\n'
