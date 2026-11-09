#!/bin/sh
set -eu

src=${TOPAZ_KERNEL_SRC:-/home/user/mitrastar-linux-5.10.260}
tc=${TOPAZ_CROSS_COMPILE:-/workspace/user-home/Desktop/MitraStar/work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-linux-}

find /home/user/openmitrastar-build -name .config -print 2>/dev/null |
while IFS= read -r cfg; do
	out=$(dirname "$cfg")
	rel=$(make -s -C "$src" O="$out" ARCH=arc CROSS_COMPILE="$tc" kernelrelease 2>/dev/null || true)
	symvers=no
	test -f "$out/Module.symvers" && symvers=yes
	printf '%s\tsymvers=%s\tout=%s\n' "$rel" "$symvers" "$out"
done
