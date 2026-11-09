#!/bin/sh
set -eu

src=${TOPAZ_KERNEL_SRC:-/home/user/mitrastar-linux-5.10.260}
tc=${TOPAZ_CROSS_COMPILE:-/workspace/user-home/Desktop/MitraStar/work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-linux-}

for out in \
	/home/user/openmitrastar-build/radiohw-probe \
	/home/user/openmitrastar-build/hgw500-controls-5g-postbaseline-20260819/kernel-out \
	/home/user/openmitrastar-build/hgw500-q1-controls-parity-20260821-oemgpio4/kernel-out \
	/home/user/openmitrastar-build/q3-f39-openlab/kernel/kernel-a \
	/home/user/openmitrastar-build/q3-f39-openlab/kernel/kernel-b \
	/home/user/openmitrastar-build/q3-f43/kernel/kernel-a \
	/home/user/openmitrastar-build/q3-f43/kernel/kernel-b \
	/home/user/openmitrastar-build/q3-persistent/kernel/kernel-a \
	/home/user/openmitrastar-build/q3-persistent/kernel/kernel-b \
	/home/user/openmitrastar-build/q3-persistent-f55/kernel/kernel-a \
	/home/user/openmitrastar-build/q3-persistent-f55/kernel/kernel-b \
	/home/user/openmitrastar-build/q3-persistent-f56/kernel/kernel-a \
	/home/user/openmitrastar-build/q3-persistent-f56/kernel/kernel-b \
	/home/user/openmitrastar-build/q3-persistent-f57/kernel/kernel-a \
	/home/user/openmitrastar-build/q3-persistent-f57/kernel/kernel-b \
	/home/user/openmitrastar-build/q3-persistent-composite-f53/kernel/kernel-a \
	/home/user/openmitrastar-build/q3-persistent-composite-f53/kernel/kernel-b \
	/home/user/openmitrastar-build/f5-autonomous-gzipinit-qtn-20260825005322/kernel-a \
	/home/user/openmitrastar-build/f5-autonomous-gzipinit-qtn-20260825005322/kernel-b \
	/home/user/openmitrastar-build/f5-safe2g-emacrxrestart-gzipinit/kernel-a \
	/home/user/openmitrastar-build/f5-safe2g-gzipinit/kernel-a
do
	if test -f "$out/.config"; then
		rel=$(make -s -C "$src" O="$out" ARCH=arc CROSS_COMPILE="$tc" kernelrelease 2>/dev/null || true)
		symvers=no
		test -f "$out/Module.symvers" && symvers=yes
		printf '%s\tsymvers=%s\tout=%s\n' "$rel" "$symvers" "$out"
	fi
done
