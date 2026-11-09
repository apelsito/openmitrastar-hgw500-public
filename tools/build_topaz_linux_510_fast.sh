#!/bin/sh
set -eu

# Fast, state-preserving RAMSSH rebuild wrapper.  The full builder remains the
# authority for creating a build tree; this script only advances an existing
# tree and never cleans it.

profile=${1:-ramssh}
case "$profile" in
	ramssh) ;;
	--check) profile=ramssh; check_only=1 ;;
	*) echo "usage: $0 [ramssh|--check]" >&2; exit 2 ;;
esac

check_only=${check_only:-0}
head_wdt=${TOPAZ_HEAD_WDT:-1}
boot_trace=${TOPAZ_BOOT_TRACE:-0}
mmu_entry_probe=${TOPAZ_MMU_ENTRY_PROBE:-0}
force_config=${TOPAZ_FAST_RECONFIGURE:-0}
force_initramfs=${TOPAZ_FAST_REBUILD_INITRAMFS:-0}

for setting in "$head_wdt" "$boot_trace" "$mmu_entry_probe" \
	"$force_config" "$force_initramfs"; do
	case "$setting" in 0|1) ;; *) echo "boolean options must be 0 or 1" >&2; exit 2 ;; esac
done
if [ "${TOPAZ_PACK_FLASH_ARTIFACTS:-0}" != 0 ]; then
	echo "ramssh is RAM-only; flash artifact packaging is forbidden" >&2
	exit 2
fi

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
src=${TOPAZ_KERNEL_SRC:-/home/user/mitrastar-linux-5.10.260}
out_root=${TOPAZ_BUILD_ROOT:-/home/user/openmitrastar-build}
out="$out_root/$profile"
init_root="$out_root/$profile-initramfs-root"
init_cpio="$out_root/$profile-initramfs.cpio"
tc="$root/work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-linux-"
configs="$root/work/kernel-port/configs"
artifacts="$root/outputs/kernel-port"
builder="$root/tools/build_topaz_linux_510.sh"
overlay_builder="$root/tools/apply_topaz_linux_510_overlay.sh"
ramssh_builder=${RAMSSH_ROOTFS_BUILDER:-$root/work/ssh-emulation/build-ramssh-rootfs.sh}
base=linux-5.10.260-topaz-ramssh-RAM-ONLY-NO-GO

case "$out" in "$out_root"/*) ;; *) echo "unsafe build path: $out" >&2; exit 3 ;; esac
test -f "$src/Makefile" || { echo "missing kernel source: $src" >&2; exit 3; }
test -x "${tc}gcc" || { echo "missing ARC toolchain: ${tc}gcc" >&2; exit 3; }
test -f "$builder" || { echo "missing full builder: $builder" >&2; exit 3; }
test -f "$overlay_builder" || { echo "missing overlay builder: $overlay_builder" >&2; exit 3; }
test -f "$ramssh_builder" || { echo "missing RAMSSH builder: $ramssh_builder" >&2; exit 3; }

if [ "$check_only" = 1 ]; then
	printf 'kernel source: %s\n' "$src"
	printf 'build output: %s\n' "$out"
	printf 'config: %s\n' "$(test -f "$out/.config" && echo present || echo missing)"
	printf 'initramfs: %s\n' "$(test -f "$init_cpio" && echo present || echo missing)"
	printf 'uImage: %s\n' "$(test -f "$out/arch/arc/boot/uImage.bin" && echo present || echo missing)"
	exit 0
fi

# A missing state is bootstrapped by the authoritative builder.  Once it
# exists, subsequent invocations stay on the selective path below.
if [ ! -f "$out/.config" ] || [ ! -f "$init_cpio" ]; then
	echo "FAST: build state missing; bootstrapping with the full RAMSSH builder"
	TOPAZ_INCREMENTAL=1 TOPAZ_PACK_FLASH_ARTIFACTS=0 \
		sh "$builder" ramssh
	exit $?
fi

lock="$out/.openmitrastar-fast-build.lock"
if ! mkdir "$lock" 2>"$out_root/.openmitrastar-lock-error.$$"; then
	if [ -d "$lock" ]; then
		echo "another RAMSSH build is active: $lock" >&2
	else
		echo "cannot create RAMSSH build lock: $lock" >&2
		cat "$out_root/.openmitrastar-lock-error.$$" >&2
	fi
	rm -f -- "$out_root/.openmitrastar-lock-error.$$"
	exit 4
fi
rm -f -- "$out_root/.openmitrastar-lock-error.$$"
shim=
cleanup()
{
	[ -z "$shim" ] || rm -rf -- "$shim"
	rmdir "$lock" 2>/dev/null || true
}
trap cleanup 0 1 2 15

export SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH:-1785024000}
export KBUILD_BUILD_TIMESTAMP="@$SOURCE_DATE_EPOCH"
export KBUILD_BUILD_USER=openmitrastar
export KBUILD_BUILD_HOST=builder
export KBUILD_BUILD_VERSION=1

# apply_topaz_linux_510_overlay.sh uses plain two-argument cp calls.  Shadow cp
# so equal files are not rewritten and therefore do not invalidate Make deps.
shim=$(mktemp -d "${TMPDIR:-/tmp}/openmitrastar-cp.XXXXXX")
cat >"$shim/cp" <<'EOF'
#!/bin/sh
if [ "$#" -eq 2 ]; then
	source_file=$1
	destination=$2
	if [ -d "$destination" ]; then
		target=$destination/$(basename -- "$source_file")
	else
		target=$destination
	fi
	if [ -f "$source_file" ] && [ -f "$target" ] && \
		cmp -s -- "$source_file" "$target"; then
		exit 0
	fi
fi
exec /bin/cp "$@"
EOF
chmod 0755 "$shim/cp"
PATH="$shim:$PATH" sh "$overlay_builder" "$src"

config_stale=$force_config
for fragment in "$configs/topaz-common.fragment" \
	"$configs/topaz-network.fragment" "$configs/topaz-ramssh.fragment"; do
	test -f "$fragment" || { echo "missing config fragment: $fragment" >&2; exit 3; }
	[ "$fragment" -ot "$out/.config" ] || config_stale=1
done
grep -qx "CONFIG_INITRAMFS_SOURCE=\"$init_cpio\"" "$out/.config" || config_stale=1
if [ "$head_wdt" = 1 ]; then
	grep -qx 'CONFIG_QTN_TOPAZ_HEAD_WDT_CANARY=y' "$out/.config" || config_stale=1
else
	grep -qx '# CONFIG_QTN_TOPAZ_HEAD_WDT_CANARY is not set' "$out/.config" || config_stale=1
fi
if [ "$boot_trace" = 1 ]; then
	grep -qx 'CONFIG_OPENMITRASTAR_BOOT_TRACE=y' "$out/.config" || config_stale=1
else
	grep -qx '# CONFIG_OPENMITRASTAR_BOOT_TRACE is not set' "$out/.config" || config_stale=1
fi
if [ "$mmu_entry_probe" = 1 ]; then
	grep -qx 'CONFIG_OPENMITRASTAR_MMU_ENTRY_PROBE=y' "$out/.config" || config_stale=1
else
	grep -qx '# CONFIG_OPENMITRASTAR_MMU_ENTRY_PROBE is not set' "$out/.config" || config_stale=1
fi

if [ "$config_stale" = 1 ]; then
	echo "FAST: refreshing RAMSSH Kconfig"
	(
		cd "$src"
		ARCH=arc CROSS_COMPILE="$tc" scripts/kconfig/merge_config.sh \
			-n -r -O "$out" "$configs/topaz-common.fragment" \
			"$configs/topaz-network.fragment" \
			"$configs/topaz-ramssh.fragment"
	)
	cfg="$src/scripts/config --file $out/.config"
	$cfg --enable BLK_DEV_INITRD --set-str INITRAMFS_SOURCE "$init_cpio"
	if [ "$head_wdt" = 1 ]; then
		$cfg --enable QTN_TOPAZ_HEAD_WDT_CANARY
	else
		$cfg --disable QTN_TOPAZ_HEAD_WDT_CANARY
	fi
	if [ "$boot_trace" = 1 ]; then
		$cfg --enable OPENMITRASTAR_BOOT_TRACE
	else
		$cfg --disable OPENMITRASTAR_BOOT_TRACE
	fi
	if [ "$mmu_entry_probe" = 1 ]; then
		$cfg --enable OPENMITRASTAR_MMU_ENTRY_PROBE
	else
		$cfg --disable OPENMITRASTAR_MMU_ENTRY_PROBE
	fi
	make -C "$src" O="$out" ARCH=arc CROSS_COMPILE="$tc" olddefconfig
else
	echo "FAST: preserving existing .config"
fi

initramfs_stale=$force_initramfs
lab=/home/user/openmitrastar-ssh-lab
keydir=/home/user/openmitrastar-ramssh-keys
for input in "$ramssh_builder" \
	"$root/work/kernel-port/initramfs/ramssh_init.c" \
	"$lab/busybox-1.38.0/busybox" \
	"$lab/dropbear-arc-multiuser-noatomic/dropbearmulti" \
	"$lab/dropbear-native/dropbearkey" \
	"$keydir/client_ed25519.pub" \
	"$keydir/dropbear_ed25519_host_key"; do
	[ -e "$input" ] || { initramfs_stale=1; continue; }
	[ "$input" -ot "$init_cpio" ] || initramfs_stale=1
done

if [ "$initramfs_stale" = 1 ]; then
	echo "FAST: rebuilding changed RAMSSH initramfs"
	SOURCE_DATE_EPOCH="$SOURCE_DATE_EPOCH" \
		RAMSSH_BOOT_ENTROPY=1 \
		sh "$ramssh_builder" "$init_root" "$init_cpio"
else
	echo "FAST: preserving existing initramfs"
fi

jobs=${TOPAZ_JOBS:-12}
case "$jobs" in ''|*[!0-9]*) echo "TOPAZ_JOBS must be a positive integer" >&2; exit 2 ;; esac
[ "$jobs" -gt 0 ] || { echo "TOPAZ_JOBS must be greater than zero" >&2; exit 2; }

echo "FAST: make -j$jobs uImage.bin"
make -C "$src" O="$out" ARCH=arc CROSS_COMPILE="$tc" \
	-j"$jobs" uImage.bin

for product in "$out/.config" "$out/vmlinux" \
	"$out/arch/arc/boot/uImage.bin" "$init_cpio" \
	"$keydir/client_ed25519.pub"; do
	test -f "$product" || { echo "missing build product: $product" >&2; exit 5; }
done
mkdir -p "$artifacts"

copy_changed()
{
	source_file=$1
	destination=$2
	if [ ! -f "$destination" ] || ! cmp -s -- "$source_file" "$destination"; then
		/bin/cp "$source_file" "$destination"
	fi
}
copy_changed "$out/.config" "$artifacts/$base.config"
copy_changed "$out/vmlinux" "$artifacts/$base.vmlinux"
copy_changed "$out/arch/arc/boot/uImage.bin" "$artifacts/$base.uImage"
copy_changed "$init_cpio" "$artifacts/$base.initramfs.cpio"
copy_changed "$keydir/client_ed25519.pub" \
	"$artifacts/$base.client_ed25519.pub"

hash_tmp="$artifacts/.$base.sha256.$$"
sha256sum "$artifacts/$base.config" "$artifacts/$base.vmlinux" \
	"$artifacts/$base.uImage" "$artifacts/$base.initramfs.cpio" \
	"$artifacts/$base.client_ed25519.pub" >"$hash_tmp"
if [ -f "$artifacts/$base.sha256" ] && \
	cmp -s -- "$hash_tmp" "$artifacts/$base.sha256"; then
	rm -f -- "$hash_tmp"
else
	mv -f -- "$hash_tmp" "$artifacts/$base.sha256"
fi

echo "FAST: complete"
cat "$artifacts/$base.sha256"
