"""Build F329 Linux 5.10 ARC watchdog integration in a private source clone.

No flash image, runtime installation, network or hardware access. Existing source,
F321/F326 artifacts and kernel build directories are never modified.
"""
from pathlib import Path
import argparse
from datetime import datetime, timezone
import hashlib
import json
import shlex
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "work/kernel-port/versions/f329-watchdog"
WS_ROOT = "/workspace/user-home/Desktop/MitraStar"
DISTRO = "podman-mem9-tidb"
KERNEL = "/home/user/mitrastar-linux-5.10.260"
BASE_CONFIG = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f321-f314-device-bound/openmitrastar-linux510-f321-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH.config"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output-dir", type=Path)
    args = ap.parse_args()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = args.output_dir or ROOT / f"outputs/kernel-port/f329-watchdog-{stamp}"
    output = output.resolve()
    if not output.is_relative_to(ROOT / "outputs") or output.exists():
        raise SystemExit("expected fresh output directory under outputs")
    output.mkdir(parents=True)
    sources = {p.relative_to(SOURCE).as_posix(): sha(p) for p in SOURCE.rglob("*") if p.is_file()}
    base_config_sha = sha(BASE_CONFIG)
    config_dest = output / "base-f321.config"
    config_dest.write_bytes(BASE_CONFIG.read_bytes())
    out_ws = WS_ROOT + "/" + output.relative_to(ROOT).as_posix()
    overlay_ws = WS_ROOT + "/" + SOURCE.relative_to(ROOT).as_posix()
    build_root = "/home/user/openmitrastar-build/f329-watchdog-" + stamp
    changed = tuple(json.loads((SOURCE / "source-origin.json").read_text())["original_sha256"])
    script = f"""
set -eu
base={shlex.quote(KERNEL)}
build={shlex.quote(build_root)}
overlay={shlex.quote(overlay_ws)}
out={shlex.quote(out_ws)}
tc={shlex.quote(WS_ROOT + '/work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-linux-')}
test ! -e "$build"
mkdir -p "$build"
cp -a "$base" "$build/linux"
src="$build/linux"
kout="$build/output"
mkdir -p "$kout"
"""
    for rel in changed:
        script += f'cp "$overlay/{rel}" "$src/{rel}"\n'
    script += """
cp "$out/base-f321.config" "$kout/.config"
"$src/scripts/kconfig/merge_config.sh" -m -O "$kout" "$kout/.config" "$overlay/watchdog.config" >"$out/config-merge.log" 2>&1
make -s -C "$src" O="$kout" ARCH=arc CROSS_COMPILE="$tc" olddefconfig >"$out/config.log" 2>&1
SOURCE_DATE_EPOCH=1790006400 KBUILD_BUILD_TIMESTAMP=@1790006400 KBUILD_BUILD_USER=openmitrastar KBUILD_BUILD_HOST=builder KBUILD_BUILD_VERSION=1 \
make -C "$src" O="$kout" ARCH=arc CROSS_COMPILE="$tc" -j8 vmlinux dtbs >"$out/build.log" 2>&1
cp "$kout/.config" "$out/f329.config"
cp "$kout/vmlinux" "$out/f329.vmlinux"
cp "$kout/arch/arc/boot/dts/topaz_mitrastar_squashfs.dtb" "$out/f329.dtb"
cp "$kout/drivers/watchdog/dw_wdt.o" "$out/dw_wdt.o"
cp "$kout/drivers/watchdog/watchdog_dev.o" "$out/watchdog_dev.o"
cp "$kout/drivers/misc/qtn-topaz-recovery.o" "$out/qtn-topaz-recovery.o"
"${tc}readelf" -h "$out/f329.vmlinux" >"$out/elf-header.txt"
"${tc}nm" "$out/f329.vmlinux" >"$out/kernel-symbols.txt"
"${tc}objdump" -dr "$out/dw_wdt.o" >"$out/dw-watchdog-disassembly.txt"
dtc -I dtb -O dts "$out/f329.dtb" >"$out/f329.decompiled.dts" 2>"$out/dtc.log"
make -s -C "$src" O="$kout" ARCH=arc CROSS_COMPILE="$tc" kernelrelease >"$out/kernelrelease.txt"
"""
    (output / "build-script.sh").write_text(script, newline="\n")
    p = subprocess.run(["wsl.exe", "-d", DISTRO, "-u", "root", "-e", "bash", "--noprofile", "--norc", out_ws + "/build-script.sh"], capture_output=True, text=True)
    (output / "launcher.log").write_text(p.stdout + p.stderr)
    result = {"schema": "openmitrastar.f329-watchdog-offline-build/v1", "created_utc": stamp,
              "status": "BUILD_FAILED", "exit_code": p.returncode,
              "input_sources": sources, "base_f321_config_sha256": base_config_sha,
              "isolated_build_directory": build_root, "hardware_access": False,
              "flash_image_created": False, "watchdog_armed": False}
    if p.returncode == 0:
        cfg = (output / "f329.config").read_text()
        required = ("CONFIG_WATCHDOG=y", "CONFIG_WATCHDOG_CORE=y", "CONFIG_DW_WATCHDOG=y", "CONFIG_WATCHDOG_NOWAYOUT=y", "# CONFIG_QTN_TOPAZ_EARLY_WDT_CANARY is not set", "# CONFIG_QTN_TOPAZ_HEAD_WDT_CANARY is not set", "# CONFIG_WATCHDOG_HANDLE_BOOT_ENABLED is not set", "# CONFIG_PM is not set")
        symbols = (output / "kernel-symbols.txt").read_text()
        missing = [line for line in required if line not in cfg.splitlines()]
        missing += [name for name in ("dw_wdt_drv_probe", "dw_wdt_start", "dw_wdt_ping", "watchdog_register_device", "do_kernel_restart") if name not in symbols]
        if "ARC" not in (output / "elf-header.txt").read_text():
            missing.append("ARC ELF")
        result["missing_contracts"] = missing
        result["status"] = "PASS_OFFLINE_BUILD_PHYSICAL_GATES_UNRUN" if not missing else "CONTRACT_FAILED"
        result["artifacts"] = {name: {"bytes": (output/name).stat().st_size, "sha256": sha(output/name)} for name in ("f329.config", "f329.vmlinux", "f329.dtb", "dw_wdt.o", "watchdog_dev.o", "qtn-topaz-recovery.o")}
    if sha(BASE_CONFIG) != base_config_sha or sources != {p.relative_to(SOURCE).as_posix(): sha(p) for p in SOURCE.rglob("*") if p.is_file()}:
        result["status"] = "INPUT_DRIFT"
    (output / "result.json").write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps({"output": str(output), "status": result["status"]}))
    return int(result["status"] != "PASS_OFFLINE_BUILD_PHYSICAL_GATES_UNRUN")


if __name__ == "__main__":
    raise SystemExit(main())
