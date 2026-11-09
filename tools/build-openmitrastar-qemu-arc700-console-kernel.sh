#!/usr/bin/env sh
set -eu

WORKSPACE="${WORKSPACE:-/workspace/user-home/Desktop/MitraStar}"
LINUX="${LINUX:-/home/user/mitrastar-linux-5.10.260}"
BUILD="${BUILD:-/home/user/openmitrastar-build/qemu-arc700-base0-nozol-validation}"
TOOLCHAIN="${TOOLCHAIN:-$WORKSPACE/work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-linux-}"
BASE_CPIO="${BASE_CPIO:-$BUILD-initramfs.no-console-20260812.cpio}"
OUT_CPIO="${OUT_CPIO:-$BUILD-initramfs.cpio}"
OUT_KERNEL="${OUT_KERNEL:-$WORKSPACE/outputs/kernel-port/linux-5.10.260-qemu-arc700-base80000000-console-validation.vmlinux}"
INIT_SOURCE="${INIT_SOURCE:-$WORKSPACE/tools/openmitrastar-qemu-init.c}"
JOBS="${JOBS:-2}"

die() {
  echo "ERROR: $*" >&2
  exit 1
}

need_file() {
  test -f "$1" || die "missing file: $1"
}

need_dir() {
  test -d "$1" || die "missing directory: $1"
}

need_exe() {
  test -x "$1" || die "missing executable: $1"
}

need_dir "$WORKSPACE"
need_dir "$LINUX"
need_dir "$BUILD"
need_file "$LINUX/usr/gen_init_cpio.c"
need_file "$BASE_CPIO"
need_file "$INIT_SOURCE"
need_exe "${TOOLCHAIN}gcc"

mkdir -p "$WORKSPACE/outputs/kernel-port" "$WORKSPACE/outputs/build"

INIT_WORK="$(mktemp -d /tmp/openmitrastar-initramfs.XXXXXX)"
GEN_INIT_CPIO="$WORKSPACE/outputs/build/gen_init_cpio"
LIST_FILE="$INIT_WORK/initramfs.list"

cleanup() {
  rm -rf "$INIT_WORK"
}
trap cleanup EXIT INT TERM

cc "$LINUX/usr/gen_init_cpio.c" -o "$GEN_INIT_CPIO"

(
  cd "$INIT_WORK"
  cpio -id --quiet < "$BASE_CPIO"
)

need_file "$INIT_WORK/init"

"${TOOLCHAIN}gcc" \
  -Os \
  -mcpu=arc700 \
  -static \
  -nostdlib \
  -ffreestanding \
  -fno-pic \
  -fno-pie \
  -fno-stack-protector \
  -Wl,--build-id=none \
  -Wl,-e,_start \
  -Wl,-Ttext=0x10000 \
  -o "$INIT_WORK/init" \
  "$INIT_SOURCE"

cat > "$LIST_FILE" <<EOF
file /init $INIT_WORK/init 0755 0 0
dir /dev 0755 0 0
nod /dev/console 0600 0 0 c 5 1
nod /dev/null 0666 0 0 c 1 3
dir /proc 0755 0 0
dir /sys 0755 0 0
EOF

"$GEN_INIT_CPIO" -t 0 "$LIST_FILE" > "$OUT_CPIO"

make ARCH=arc CROSS_COMPILE="$TOOLCHAIN" O="$BUILD" -C "$LINUX" olddefconfig
make ARCH=arc CROSS_COMPILE="$TOOLCHAIN" O="$BUILD" -C "$LINUX" -j"$JOBS" vmlinux

cp -f "$BUILD/vmlinux" "$OUT_KERNEL"

echo "Built: $OUT_KERNEL"
sha256sum "$OUT_KERNEL" "$OUT_CPIO"
