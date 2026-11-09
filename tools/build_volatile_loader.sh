#!/bin/sh
set -eu

incremental=${OMVL_INCREMENTAL:-0}
case "$incremental" in 0|1) ;; *) echo "OMVL_INCREMENTAL must be 0 or 1" >&2; exit 2 ;; esac

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
src="$root/work/volatile-loader"
gpl_repo="$root/work/sources/Quantenna-GPL"
live_config="$root/outputs/kernel-port/live-kernel-2.6.35.12.config"
image="$root/outputs/kernel-port/linux-5.10.260-topaz-ramssh-RAM-ONLY-NO-GO.uImage"
tc="$root/work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-linux-"
build="$src/build"
gpl_build="$build/Quantenna-GPL"
kernel="$gpl_build/linux_2.6.35.12"
kernel_build="$build/oem-kernel"
out="$src/out"

for required in "$gpl_repo/.git" "$live_config" "$image" "${tc}gcc" \
	"$src/volatile_loader.c" "$src/trampoline.S" "$src/omvlctl.c" "$src/preflight.py"; do
	test -e "$required" || { echo "missing input: $required" >&2; exit 2; }
done
case "$build" in "$src"/*) ;; *) exit 3 ;; esac
case "$out" in "$src"/*) ;; *) exit 3 ;; esac
rm -rf -- "$out"
mkdir -p "$out"
if [ "$incremental" = 0 ]; then
	rm -rf -- "$build"
	mkdir -p "$gpl_build" "$kernel_build"
else
	test -f "$kernel_build/include/generated/autoconf.h"
	test -f "$kernel_build/Makefile"
fi

python3 -m unittest discover -s "$src" -p 'test_*.py' -v 2>&1 | tee "$out/host-tests.log"
python3 "$src/preflight.py" "$image" | tee "$out/pinned-uimage-preflight.json"

# The working GPL checkout is intentionally sparse and omits generic kernel
# build scripts. Materialize the pinned commit into the disposable build tree;
# this also keeps every generated file inside work/volatile-loader/**.
if [ "$incremental" = 0 ]; then
	git -c safe.directory="$gpl_repo" -C "$gpl_repo" archive HEAD | tar -xf - -C "$gpl_build" \
		--exclude='linux_2.6.35.12/Documentation*' \
		--exclude='buildroot*' --exclude='package*' \
		--exclude='*.tar' --exclude='*.zip'
	# The sparse GPL checkout carries this generated build helper outside the
	# archived commit. Keep the disposable build self-contained.
	cp "$gpl_repo/linux_2.6.35.12/qtn_optfilter.pl" \
		"$gpl_build/linux_2.6.35.12/qtn_optfilter.pl"
	cp "$gpl_repo/linux_2.6.35.12/qtn_optfilter.pl" "$kernel_build/qtn_optfilter.pl"
	cp "$gpl_build/linux_2.6.35.12/include/linux/compiler-gcc4.h" \
		"$gpl_build/linux_2.6.35.12/include/linux/compiler-gcc15.h"
	make -C "$gpl_build" board_config=topaz_dbdc_config board_platform=topaz \
		common/current_platform.h.tmp >"$out/platform-header.log" 2>&1
	test -f "$gpl_build/common/current_platform.h"
	cp "$live_config" "$kernel_build/.config"
	make -C "$kernel" O="$kernel_build" ARCH=arc CROSS_COMPILE="$tc" \
		KCFLAGS=-std=gnu89 oldconfig </dev/null >"$out/kernel-oldconfig.log" 2>&1
	make -C "$kernel" O="$kernel_build" ARCH=arc CROSS_COMPILE="$tc" \
		KCFLAGS=-std=gnu89 prepare scripts >"$out/kernel-prepare.log" 2>&1
fi
make -C "$kernel" O="$kernel_build" ARCH=arc CROSS_COMPILE="$tc" \
	M="$src" clean >/dev/null
make -C "$kernel" O="$kernel_build" ARCH=arc CROSS_COMPILE="$tc" \
	KCFLAGS=-std=gnu89 M="$src" KBUILD_MODPOST_WARN=1 modules >"$out/module-build.log" 2>&1

"${tc}gcc" -static -Os -s -Wall -Wextra -Werror -I"$src" \
	-o "$out/omvlctl" "$src/omvlctl.c"
cp "$src/openmitrastar_volatile_loader.ko" "$out/"
"${tc}readelf" -h "$out/openmitrastar_volatile_loader.ko" >"$out/module-elf-header.txt"
"${tc}readelf" -rW "$out/openmitrastar_volatile_loader.ko" >"$out/module-relocations.txt"
"${tc}readelf" -r "$src/trampoline.o" >"$out/trampoline-relocations.txt"
"${tc}nm" -u "$out/openmitrastar_volatile_loader.ko" >"$out/module-undefined-symbols.txt"
"${tc}objdump" -d "$src/trampoline.o" >"$out/trampoline-disassembly.txt"
"${tc}size" "$out/openmitrastar_volatile_loader.ko" "$out/omvlctl" >"$out/sizes.txt"

grep -Eq 'Machine:.*(ARC|ARCompact)' "$out/module-elf-header.txt"
if grep -Eq 'R_ARC|RELOCATION RECORDS FOR' "$out/trampoline-relocations.txt"; then
	echo "trampoline contains relocations" >&2; exit 4
fi
if awk '/R_ARC_/ && $3 != "R_ARC_32" && $3 != "R_ARC_32_ME" { bad = 1 }
        END { exit bad ? 0 : 1 }' "$out/module-relocations.txt"; then
	echo "module contains relocations unsupported by OEM Linux 2.6.35" >&2
	grep 'R_ARC_' "$out/module-relocations.txt" | \
		grep -Ev ' R_ARC_32(_ME)? ' >&2 || true
	exit 7
fi
if grep -Eqi '(mtd|bootcfg|saveenv|flash_erase|nandwrite)' "$out/module-undefined-symbols.txt"; then
	echo "persistent-storage dependency found" >&2; exit 5
fi
if strings "$out/openmitrastar_volatile_loader.ko" | \
	grep -Eqi '(/dev/mtd|bootcfg|saveenv|flash_erase|nandwrite)'; then
	echo "persistent-storage string found" >&2; exit 6
fi
strings "$out/openmitrastar_volatile_loader.ko" | grep '^vermagic=' >"$out/vermagic.txt"
grep -q '^vermagic=2.6.35.12 ' "$out/vermagic.txt"
(cd "$out" && sha256sum openmitrastar_volatile_loader.ko omvlctl \
	module-undefined-symbols.txt trampoline-disassembly.txt \
	module-relocations.txt pinned-uimage-preflight.json >SHA256SUMS)

doc="$out/OPENMITRASTAR_VOLATILE_LOADER_FULL.md"
cp "$src/README.md" "$doc"
cat >>"$doc" <<'EOF'

## Exact build evidence

`SHA256SUMS`, ELF header, vermagic, undefined-symbol list, relocation audit and
disassembly are adjacent to this document.

## Complete source snapshot
EOF
append_source() {
	path=$1; language=$2
	printf '\n### `%s`\n\n```%s\n' "$path" "$language" >>"$doc"
	cat "$root/$path" >>"$doc"
	printf '\n```\n' >>"$doc"
}
append_source work/volatile-loader/omvl_uapi.h c
append_source work/volatile-loader/volatile_loader.c c
append_source work/volatile-loader/trampoline.S asm
append_source work/volatile-loader/omvlctl.c c
append_source work/volatile-loader/preflight.py python
append_source work/volatile-loader/test_preflight.py python
append_source work/volatile-loader/Makefile make
append_source tools/build_volatile_loader.sh sh

printf 'OMVL_OFFLINE_BUILD_PASS\nmodule=%s\nhandoff=%s\n' \
	"$out/openmitrastar_volatile_loader.ko" "$doc"
