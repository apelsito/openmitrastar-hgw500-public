#!/usr/bin/env python3
"""Build offline F300 from F299 with a two-sample hardware-demand trigger."""
from __future__ import annotations

import argparse
import atexit
import hashlib
import json
from pathlib import Path
import re
import shlex
import shutil

import build_f293_emac_hw_rx_demand_from_f292 as f293


ROOT = Path(__file__).resolve().parents[1]
BASE_DRIVER = ROOT / "work/kernel-port/linux-5.10/drivers/net/ethernet/qtn/qtn-topaz-emac-f293-hw-rx-demand.c"
DTS = ROOT / "work/kernel-port/linux-5.10/arch/arc/boot/dts/topaz_mitrastar_storage_probe.dts"
KERNEL_SRC = "/home/user/mitrastar-linux-5.10.260"
WS_ROOT = "/workspace/user-home/Desktop/MitraStar"
ROOTFS_WINDOW = 0x460000
STORE_SLOT_OFFSET = 0x5E0000
STORE_SIZE = 0x1C0000
EARLY_RESTART_SAMPLES = 2


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise ValueError(f"F300 patch anchor {label!r} matched {count} times")
    return source.replace(old, new, 1)


def render_f300_driver(source: str) -> str:
    """Derive F300 in memory without mutating the F299 builder or source."""
    source = replace_once(
        source,
        "#define QTN_TOPAZ_EMAC_RX_RESTART_POKES\t16\n",
        "#define QTN_TOPAZ_EMAC_RX_RESTART_POKES\t16\n"
        "#define QTN_TOPAZ_EMAC_RX_DEMAND_RESTART_SAMPLES\t2\n",
        "early restart threshold",
    )
    source = replace_once(
        source,
        "\tu32 poll_mac_rx_progress_observations;\n"
        "\tu32 poll_mac_rx_read_failures;\n",
        "\tu32 poll_mac_rx_progress_observations;\n"
        "\tu32 poll_mac_rx_progress_streak;\n"
        "\tu32 poll_mac_rx_progress_streak_max;\n"
        "\tu32 poll_mac_rx_read_failures;\n",
        "MAC progress streak state",
    )
    source = replace_once(
        source,
        "\tu32 rx_restart_reason_stagnant;\n"
        "\tu32 rx_restart_last_dma_status;\n",
        "\tu32 rx_restart_reason_stagnant;\n"
        "\tu32 rx_restart_reason_hw_demand;\n"
        "\tu32 rx_restart_last_dma_status;\n",
        "hardware-demand restart counter",
    )
    source = replace_once(
        source,
        "\tu32 rx_restart_last_mac_rx_progress_age_ms;\n"
        "\tu32 rx_restart_last_dma_missed_frames;\n",
        "\tu32 rx_restart_last_mac_rx_progress_age_ms;\n"
        "\tu32 rx_restart_last_mac_rx_progress_streak;\n"
        "\tu32 rx_restart_last_trigger_pokes;\n"
        "\tu32 rx_restart_last_dma_missed_frames;\n",
        "restart trigger telemetry state",
    )
    source = replace_once(
        source,
        "\t\t\"rx_restart_reason_stagnant=%u\\nrx_restart_throttled=%u\\n\"\n",
        "\t\t\"rx_restart_reason_stagnant=%u\\nrx_restart_reason_hw_demand=%u\\n\"\n"
        "\t\t\"rx_restart_throttled=%u\\n\"\n",
        "restart reason telemetry format",
    )
    source = replace_once(
        source,
        "\t\t\"mac_rx_samples=%u\\nmac_rx_progress_observations=%u\\n\"\n"
        "\t\t\"mac_rx_progress_age_ms=%lu\\nmac_rx_read_failures=%u\\n\"\n",
        "\t\t\"mac_rx_samples=%u\\nmac_rx_progress_observations=%u\\n\"\n"
        "\t\t\"mac_rx_progress_streak=%u\\nmac_rx_progress_streak_max=%u\\n\"\n"
        "\t\t\"mac_rx_progress_age_ms=%lu\\nmac_rx_read_failures=%u\\n\"\n",
        "MAC progress streak telemetry format",
    )
    source = replace_once(
        source,
        "\t\t\"rx_restart_last_mac_rx_progress_age_ms=%u\\n\"\n"
        "\t\t\"rx_restart_last_dma_missed_frames=%u\\n\"\n",
        "\t\t\"rx_restart_last_mac_rx_progress_age_ms=%u\\n\"\n"
        "\t\t\"rx_restart_last_mac_rx_progress_streak=%u\\n\"\n"
        "\t\t\"rx_restart_last_trigger_pokes=%u\\n\"\n"
        "\t\t\"rx_restart_last_dma_missed_frames=%u\\n\"\n",
        "restart trigger telemetry format",
    )
    source = replace_once(
        source,
        "\t\tREAD_ONCE(emac->rx_restart_reason_stagnant),\n"
        "\t\tREAD_ONCE(emac->poll_rx_restart_throttled),\n",
        "\t\tREAD_ONCE(emac->rx_restart_reason_stagnant),\n"
        "\t\tREAD_ONCE(emac->rx_restart_reason_hw_demand),\n"
        "\t\tREAD_ONCE(emac->poll_rx_restart_throttled),\n",
        "restart reason telemetry argument",
    )
    source = replace_once(
        source,
        "\t\tREAD_ONCE(emac->poll_mac_rx_progress_observations),\n"
        "\t\tlast_mac_rx_progress_age_ms,\n",
        "\t\tREAD_ONCE(emac->poll_mac_rx_progress_observations),\n"
        "\t\tREAD_ONCE(emac->poll_mac_rx_progress_streak),\n"
        "\t\tREAD_ONCE(emac->poll_mac_rx_progress_streak_max),\n"
        "\t\tlast_mac_rx_progress_age_ms,\n",
        "MAC progress streak telemetry arguments",
    )
    source = replace_once(
        source,
        "\t\tREAD_ONCE(emac->rx_restart_last_mac_rx_progress_age_ms),\n"
        "\t\tREAD_ONCE(emac->rx_restart_last_dma_missed_frames),\n",
        "\t\tREAD_ONCE(emac->rx_restart_last_mac_rx_progress_age_ms),\n"
        "\t\tREAD_ONCE(emac->rx_restart_last_mac_rx_progress_streak),\n"
        "\t\tREAD_ONCE(emac->rx_restart_last_trigger_pokes),\n"
        "\t\tREAD_ONCE(emac->rx_restart_last_dma_missed_frames),\n",
        "restart trigger telemetry arguments",
    )
    source = replace_once(
        source,
        "\tbool rx_restart_throttled = false;\n"
        "\tu32 rx_head_status = 0;\n",
        "\tbool rx_restart_throttled = false;\n"
        "\tbool hw_rx_demand_restart = false;\n"
        "\tu32 rx_head_status = 0;\n",
        "hardware-demand restart decision",
    )
    source = replace_once(
        source,
        "\tif (progress) {\n"
        "\t\temac->poll_last_rx_packets = packets;\n"
        "\t\temac->poll_last_progress_jiffies = jiffies;\n"
        "\t}\n",
        "\tif (progress) {\n"
        "\t\temac->poll_last_rx_packets = packets;\n"
        "\t\temac->poll_last_progress_jiffies = jiffies;\n"
        "\t\temac->poll_mac_rx_progress_streak = 0;\n"
        "\t}\n",
        "Linux RX progress resets demand streak",
    )
    source = replace_once(
        source,
        "\t\tif (cur_rx == emac->poll_last_cur_rx)\n"
        "\t\t\temac->poll_same_cur_rx_pokes++;\n"
        "\t\telse\n"
        "\t\t\temac->poll_same_cur_rx_pokes = 0;\n",
        "\t\tif (cur_rx == emac->poll_last_cur_rx) {\n"
        "\t\t\temac->poll_same_cur_rx_pokes++;\n"
        "\t\t} else {\n"
        "\t\t\temac->poll_same_cur_rx_pokes = 0;\n"
        "\t\t\temac->poll_mac_rx_progress_streak = 0;\n"
        "\t\t}\n",
        "stalled descriptor pointer streak",
    )
    source = replace_once(
        source,
        "\t\t\t\tif (mac_rx_delta) {\n"
        "\t\t\t\t\temac->poll_mac_rx_progress_observations++;\n"
        "\t\t\t\t\temac->poll_last_mac_rx_progress_jiffies = jiffies;\n"
        "\t\t\t\t}\n",
        "\t\t\t\tif (mac_rx_delta && emac->poll_same_cur_rx_pokes) {\n"
        "\t\t\t\t\temac->poll_mac_rx_progress_observations++;\n"
        "\t\t\t\t\tif (emac->poll_mac_rx_progress_streak != U32_MAX)\n"
        "\t\t\t\t\t\temac->poll_mac_rx_progress_streak++;\n"
        "\t\t\t\t\temac->poll_mac_rx_progress_streak_max = max(\n"
        "\t\t\t\t\t\temac->poll_mac_rx_progress_streak_max,\n"
        "\t\t\t\t\t\temac->poll_mac_rx_progress_streak);\n"
        "\t\t\t\t\temac->poll_last_mac_rx_progress_jiffies = jiffies;\n"
        "\t\t\t\t} else {\n"
        "\t\t\t\t\temac->poll_mac_rx_progress_streak = 0;\n"
        "\t\t\t\t}\n",
        "consecutive hardware progress tracking",
    )
    source = replace_once(
        source,
        "\t\t} else {\n"
        "\t\t\temac->poll_mac_rx_read_failures++;\n"
        "\t\t}\n"
        "\t\tdma_missed_frames = qtn_emac_read(emac,\n",
        "\t\t} else {\n"
        "\t\t\temac->poll_mac_rx_read_failures++;\n"
        "\t\t\temac->poll_mac_rx_progress_streak = 0;\n"
        "\t\t}\n"
        "\t\tdma_missed_frames = qtn_emac_read(emac,\n",
        "read failure resets demand streak",
    )
    source = replace_once(
        source,
        "\t\tif (rx_head_status & QTN_EMAC_DESC_OWN)\n"
        "\t\t\temac->rx_head_dma_owned_samples++;\n"
        "\t\telse\n"
        "\t\t\temac->rx_head_cpu_owned_descs++;\n"
        "\t\tif (!(rx_head_status & QTN_EMAC_DESC_OWN)) {\n",
        "\t\tif (rx_head_status & QTN_EMAC_DESC_OWN)\n"
        "\t\t\temac->rx_head_dma_owned_samples++;\n"
        "\t\telse\n"
        "\t\t\temac->rx_head_cpu_owned_descs++;\n"
        "\t\thw_rx_demand_restart =\n"
        "\t\t\temac->poll_same_cur_rx_pokes >=\n"
        "\t\t\t\tQTN_TOPAZ_EMAC_RX_DEMAND_RESTART_SAMPLES &&\n"
        "\t\t\temac->poll_same_cur_rx_pokes <\n"
        "\t\t\t\tQTN_TOPAZ_EMAC_RX_RESTART_POKES &&\n"
        "\t\t\temac->poll_mac_rx_progress_streak >=\n"
        "\t\t\t\tQTN_TOPAZ_EMAC_RX_DEMAND_RESTART_SAMPLES;\n"
        "\t\tif (!(rx_head_status & QTN_EMAC_DESC_OWN)) {\n",
        "strict hardware-demand gate",
    )
    source = replace_once(
        source,
        "\t\t} else if (emac->poll_same_cur_rx_pokes >=\n"
        "\t\t\t\tQTN_TOPAZ_EMAC_RX_RESTART_POKES) {\n",
        "\t\t} else if (emac->poll_same_cur_rx_pokes >=\n"
        "\t\t\t\tQTN_TOPAZ_EMAC_RX_RESTART_POKES ||\n"
        "\t\t\t   hw_rx_demand_restart) {\n",
        "F290 fallback plus early demand gate",
    )
    source = replace_once(
        source,
        "\t\t\temac->rx_restart_last_mac_rx_progress_age_ms =\n"
        "\t\t\t\temac->poll_mac_rx_progress_observations ?\n"
        "\t\t\t\tmin_t(unsigned long,\n"
        "\t\t\t\t      jiffies_to_msecs(jiffies -\n"
        "\t\t\t\t\temac->poll_last_mac_rx_progress_jiffies),\n"
        "\t\t\t\t      U32_MAX) : U32_MAX;\n"
        "\t\t\temac->rx_restart_last_dma_missed_frames =\n",
        "\t\t\temac->rx_restart_last_mac_rx_progress_age_ms =\n"
        "\t\t\t\temac->poll_mac_rx_progress_observations ?\n"
        "\t\t\t\tmin_t(unsigned long,\n"
        "\t\t\t\t      jiffies_to_msecs(jiffies -\n"
        "\t\t\t\t\temac->poll_last_mac_rx_progress_jiffies),\n"
        "\t\t\t\t      U32_MAX) : U32_MAX;\n"
        "\t\t\temac->rx_restart_last_mac_rx_progress_streak =\n"
        "\t\t\t\temac->poll_mac_rx_progress_streak;\n"
        "\t\t\temac->rx_restart_last_trigger_pokes =\n"
        "\t\t\t\temac->poll_same_cur_rx_pokes;\n"
        "\t\t\temac->rx_restart_last_dma_missed_frames =\n",
        "restart trigger snapshot",
    )
    source = replace_once(
        source,
        "\t\t\tif (dma_status & QTN_EMAC_DMA_IRQ_RX_STOPPED)\n"
        "\t\t\t\temac->rx_restart_reason_stopped++;\n",
        "\t\t\tif (hw_rx_demand_restart)\n"
        "\t\t\t\temac->rx_restart_reason_hw_demand++;\n"
        "\t\t\telse if (dma_status & QTN_EMAC_DMA_IRQ_RX_STOPPED)\n"
        "\t\t\t\temac->rx_restart_reason_stopped++;\n",
        "hardware-demand restart classification",
    )
    source = replace_once(
        source,
        "\t\t\tqtn_emac_restart_rx_dma(emac, dma_ctrl);\n"
        "\t\t\temac->poll_same_cur_rx_pokes = 0;\n"
        "\t\t\temac->poll_last_progress_jiffies = jiffies;\n"
        "\t\t\temac->poll_last_rx_restart_jiffies = jiffies;\n"
        "\t\t\trx_restarted = true;\n",
        "\t\t\tqtn_emac_restart_rx_dma(emac, dma_ctrl);\n"
        "\t\t\temac->poll_same_cur_rx_pokes = 0;\n"
        "\t\t\temac->poll_last_progress_jiffies = jiffies;\n"
        "\t\t\temac->poll_last_rx_restart_jiffies = jiffies;\n"
        "\t\t\trx_restarted = true;\n"
        "\t\t\temac->poll_mac_rx_progress_streak = 0;\n",
        "post-restart streak reset",
    )
    source = replace_once(
        source,
        "\temac->poll_mac_rx_progress_observations = 0;\n"
        "\temac->poll_mac_rx_read_failures = 0;\n",
        "\temac->poll_mac_rx_progress_observations = 0;\n"
        "\temac->poll_mac_rx_progress_streak = 0;\n"
        "\temac->poll_mac_rx_progress_streak_max = 0;\n"
        "\temac->poll_mac_rx_read_failures = 0;\n",
        "open-time streak initialization",
    )
    source = replace_once(
        source,
        "\temac->rx_restart_reason_stagnant = 0;\n"
        "\temac->rx_restart_last_dma_status = 0;\n",
        "\temac->rx_restart_reason_stagnant = 0;\n"
        "\temac->rx_restart_reason_hw_demand = 0;\n"
        "\temac->rx_restart_last_dma_status = 0;\n",
        "open-time reason initialization",
    )
    source = replace_once(
        source,
        "\temac->rx_restart_last_mac_rx_progress_age_ms = 0;\n"
        "\temac->rx_restart_last_dma_missed_frames = 0;\n",
        "\temac->rx_restart_last_mac_rx_progress_age_ms = 0;\n"
        "\temac->rx_restart_last_mac_rx_progress_streak = 0;\n"
        "\temac->rx_restart_last_trigger_pokes = 0;\n"
        "\temac->rx_restart_last_dma_missed_frames = 0;\n",
        "open-time trigger initialization",
    )
    return source


def wsl_path(path: Path) -> str:
    value = path.resolve().as_posix()
    drive, tail = value.split(":/", 1)
    return f"/mnt/{drive.lower()}/{tail}"


def build_kernel(assets: Path, source_config: Path, driver: Path, distro: str) -> None:
    kernel_out = "/home/user/openmitrastar-build/f300-emac-hw-demand-two-sample"
    canonical_dts = ROOT / "work/kernel-port/linux-5.10/arch/arc/boot/dts/topaz_mitrastar_squashfs.dts"
    canonical_driver = ROOT / "work/kernel-port/linux-5.10/drivers/net/ethernet/qtn/qtn-topaz-emac.c"
    shell = f'''
set -eu
src={shlex.quote(KERNEL_SRC)}
out={shlex.quote(kernel_out)}
assets={shlex.quote(wsl_path(assets))}
tc={shlex.quote(WS_ROOT + '/work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-linux-')}
restore_dts={shlex.quote(wsl_path(canonical_dts))}
restore_driver={shlex.quote(wsl_path(canonical_driver))}
trap 'cp "$restore_dts" "$src/arch/arc/boot/dts/topaz_mitrastar_squashfs.dts"; cp "$restore_driver" "$src/drivers/net/ethernet/qtn/qtn-topaz-emac.c"' EXIT HUP INT TERM
rm -rf "$out"
mkdir -p "$out" "$assets"
cp {shlex.quote(wsl_path(DTS))} "$src/arch/arc/boot/dts/topaz_mitrastar_squashfs.dts"
cp {shlex.quote(wsl_path(driver))} "$src/drivers/net/ethernet/qtn/qtn-topaz-emac.c"
grep -q '^#define QTN_TOPAZ_EMAC_RX_RING_COUNT[[:space:]]*256$' "$src/drivers/net/ethernet/qtn/qtn-topaz-emac.c"
grep -q '^#define QTN_TOPAZ_EMAC_NAPI_WEIGHT[[:space:]]*256$' "$src/drivers/net/ethernet/qtn/qtn-topaz-emac.c"
grep -q '^#define QTN_TOPAZ_EMAC_RX_RESTART_POKES[[:space:]]*16$' "$src/drivers/net/ethernet/qtn/qtn-topaz-emac.c"
grep -q '^#define QTN_TOPAZ_EMAC_RX_DEMAND_RESTART_SAMPLES[[:space:]]*2$' "$src/drivers/net/ethernet/qtn/qtn-topaz-emac.c"
cp {shlex.quote(wsl_path(source_config))} "$out/.config"
"$src/scripts/config" --file "$out/.config" --set-str INITRAMFS_SOURCE "" --set-str ARC_BUILTIN_DTB_NAME topaz_mitrastar_squashfs
make -s -C "$src" O="$out" ARCH=arc CROSS_COMPILE="$tc" olddefconfig
SOURCE_DATE_EPOCH=1785024000 KBUILD_BUILD_TIMESTAMP=@1785024000 KBUILD_BUILD_USER=openmitrastar KBUILD_BUILD_HOST=builder KBUILD_BUILD_VERSION=1 make -C "$src" O="$out" ARCH=arc CROSS_COMPILE="$tc" -j12 vmlinux uImage.bin dtbs > "$assets/kernel-build.log" 2>&1
cp "$out/.config" "$assets/kernel-squashfs.config"
cp "$out/vmlinux" "$assets/kernel-squashfs.vmlinux"
cp "$out/arch/arc/boot/uImage.bin" "$assets/kernel-squashfs.uncompressed.uImage"
cp "$out/arch/arc/boot/dts/topaz_mitrastar_squashfs.dtb" "$assets/topaz_mitrastar_squashfs.dtb"
'''
    f293.run_wsl(shell, distro)
    uimage = assets / "kernel-squashfs.uncompressed.uImage"
    raw = assets / "kernel-squashfs.raw.bin"
    raw.write_bytes(uimage.read_bytes()[64:])
    from build_f71_qcsapi_interp_from_f70 import encode_lzma_legacy
    (assets / "kernel-squashfs.lzma").write_bytes(encode_lzma_legacy(raw))


def verify_source_contract(source: str) -> None:
    required = (
        "#define QTN_TOPAZ_EMAC_RX_RING_COUNT\t256",
        "#define QTN_TOPAZ_EMAC_NAPI_WEIGHT\t256",
        "#define QTN_TOPAZ_EMAC_RX_RESTART_POKES\t16",
        "#define QTN_TOPAZ_EMAC_RX_RESTART_COOLDOWN_MS\t10000",
        "#define QTN_TOPAZ_EMAC_RX_DEMAND_RESTART_SAMPLES\t2",
        "poll_mac_rx_progress_streak",
        "rx_restart_reason_hw_demand",
        "hw_rx_demand_restart",
    )
    missing = [marker for marker in required if marker not in source]
    if missing:
        raise SystemExit(f"F300 source contract missing: {missing}")
    if source.count("qtn_emac_restart_rx_dma(emac, dma_ctrl);") != 1:
        raise SystemExit("F300 must retain exactly one F290 restart action")
    if "QTN_TOPAZ_EMAC_RX_FAULT_MEMORY_MS" in source or "recent_rx_fault" in source:
        raise SystemExit("F300 must not restore the rejected F291 remembered-fault gate")
    gate = re.search(
        r"else if \(emac->poll_same_cur_rx_pokes >=\s*"
        r"QTN_TOPAZ_EMAC_RX_RESTART_POKES \|\|\s*hw_rx_demand_restart\)",
        source,
    )
    if gate is None:
        raise SystemExit("F300 does not preserve the F290 16-poke fallback")


def verify_binary_contract(vmlinux: Path, distro: str) -> dict[str, object]:
    contract = f293.verify_binary_contract(vmlinux, distro)
    telemetry = (
        "mac_rx_progress_streak=",
        "mac_rx_progress_streak_max=",
        "rx_restart_reason_hw_demand=",
        "rx_restart_last_mac_rx_progress_streak=",
        "rx_restart_last_trigger_pokes=",
    )
    image = vmlinux.read_bytes()
    missing = [marker for marker in telemetry if marker.encode("ascii") not in image]
    if missing:
        raise SystemExit(f"F300 binary contract missing early-recovery telemetry: {missing}")
    contract.update({
        "schema": "openmitrastar.f300-emac-hw-demand-two-sample-binary-contract/v1",
        "fallback_restart_pokes": 16,
        "early_restart_samples": EARLY_RESTART_SAMPLES,
        "early_restart_telemetry": list(telemetry),
    })
    return contract


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device-id", default="hgw500bna-qcv2-a2-primary")
    parser.add_argument("--identity-root", type=Path, default=f293.DEFAULT_ROOT)
    parser.add_argument("--private-output-root", type=Path, default=Path.home() / ".openmitrastar/devices")
    parser.add_argument("--distro", default="podman-mem9-tidb")
    parser.add_argument("--dropbearkey", default=f293.DEFAULT_TOOL)
    parser.add_argument("--replace-existing", action="store_true")
    args = parser.parse_args()
    if not f293.DEVICE_RE.fullmatch(args.device_id):
        raise SystemExit("invalid --device-id")

    base_source = BASE_DRIVER.read_text(encoding="utf-8")
    driver_source = render_f300_driver(base_source)
    verify_source_contract(driver_source)

    firmware_root = args.private_output_root.resolve() / args.device_id / "firmware"
    source = firmware_root / "f299-device-bound"
    source_base = f"openmitrastar-linux510-f299-{args.device_id}-PRIVATE-NO-FLASH"
    source_manifest = json.loads((source / "manifest.json").read_text(encoding="ascii"))
    final_out = firmware_root / "f300-device-bound"
    if final_out.exists() and not args.replace_existing:
        raise SystemExit(f"refusing to overwrite private firmware: {final_out}")
    if final_out.exists():
        if final_out.name != "f300-device-bound" or final_out.parent != firmware_root:
            raise SystemExit(f"unsafe replacement target: {final_out}")
        shutil.rmtree(final_out)

    identity_dir = args.identity_root.resolve() / args.device_id
    identity = json.loads((identity_dir / "identity.json").read_text(encoding="utf-8"))
    key = identity_dir / "dropbear_ed25519_host_key"
    public_key = (identity_dir / identity["public_key_file"]).read_text(encoding="ascii").strip()
    if f293.inspect_key(args.distro, args.dropbearkey, key) != identity["fingerprint"]:
        raise SystemExit("device identity mismatch")

    scratch = ROOT / ".codex_tmp" / f"f300-device-{args.device_id}"
    if scratch.exists():
        shutil.rmtree(scratch)

    def cleanup() -> None:
        if scratch.exists():
            shutil.rmtree(scratch)

    atexit.register(cleanup)
    source_build = scratch / "source-build"
    overlay = scratch / "foundation/overlay"
    assets = scratch / "assets"
    kernel_assets = scratch / "kernel-assets"
    output = scratch / "build"
    generated_driver = scratch / "qtn-topaz-emac-f300-hw-demand-two-sample.c"
    shutil.copytree(source, source_build)
    overlay.mkdir(parents=True, exist_ok=True)
    generated_driver.write_text(driver_source, encoding="utf-8", newline="\n")

    base = f"openmitrastar-linux510-f300-{args.device_id}-PRIVATE-NO-FLASH"
    names = (
        "SOURCE_BUILD", "SOURCE_BASE", "FOUNDATION", "OVERLAY", "ASSETS", "OUT", "BASE",
        "PRODUCT_VERSION", "ASSETS_SCHEMA", "DIFF_SCHEMA", "REMOVE_PATHS", "DISTRO",
    )
    old = {name: getattr(f293.foundation, name) for name in names}
    old_rootfs_window = f293.compose_engine.ROOTFS_WINDOW
    try:
        f293.foundation.SOURCE_BUILD = source_build
        f293.foundation.SOURCE_BASE = source_base
        f293.foundation.FOUNDATION = overlay.parent
        f293.foundation.OVERLAY = overlay
        f293.foundation.ASSETS = assets
        f293.foundation.OUT = output
        f293.foundation.BASE = base
        f293.foundation.PRODUCT_VERSION = "lyoko-foundation-6.5.3-f300-emac-hw-demand-two-sample-device"
        f293.foundation.ASSETS_SCHEMA = "openmitrastar.f300-emac-hw-demand-two-sample-device-assets/v1"
        f293.foundation.DIFF_SCHEMA = "openmitrastar.f300-emac-hw-demand-two-sample-device-rootfs-diff/v1"
        f293.foundation.REMOVE_PATHS = ()
        f293.foundation.DISTRO = args.distro
        f293.compose_engine.ROOTFS_WINDOW = ROOTFS_WINDOW
        assets_report = f293.foundation.prepare_assets()
        build_kernel(kernel_assets, source / f"{source_base}.config", generated_driver, args.distro)
        for asset_name in (
            "kernel-squashfs.uncompressed.uImage",
            "kernel-squashfs.raw.bin",
            "kernel-squashfs.lzma",
            "kernel-squashfs.config",
            "topaz_mitrastar_squashfs.dtb",
            "kernel-squashfs.vmlinux",
        ):
            shutil.copy2(kernel_assets / asset_name, assets / asset_name)
        with f293.foundation.variant_context():
            rc = f293.foundation.engine.main()
    finally:
        f293.compose_engine.ROOTFS_WINDOW = old_rootfs_window
        for name, value in old.items():
            setattr(f293.foundation, name, value)
    if rc:
        raise SystemExit(rc)

    manifest_path = output / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="ascii"))
    rootfs = output / f"{base}.rootfs.squashfs"
    f293.verify_embedded_key(rootfs, identity["fingerprint"], args.distro, args.dropbearkey, scratch)
    changed_paths = set(assets_report["rootfs_diff"]["changed_paths"])
    if changed_paths != {"etc/openmitrastar/release"}:
        raise SystemExit(f"F300 rootfs change is not release-only: {sorted(changed_paths)}")
    if sha256(output / f"{base}.kernel.lzma") == sha256(source / f"{source_base}.kernel.lzma"):
        raise SystemExit("F300 kernel did not change from F299")
    for suffix in (".config", ".dtb"):
        if sha256(output / f"{base}{suffix}") != sha256(source / f"{source_base}{suffix}"):
            raise SystemExit(f"F300 unexpectedly changed {suffix}")

    binary_contract = verify_binary_contract(output / f"{base}.vmlinux", args.distro)
    candidate = output / manifest["artifacts"]["webformat"]["file"]
    candidate_data = candidate.read_bytes()
    full_slot = candidate_data + b"\xff" * (0x7A0000 - len(candidate_data))
    store_erased = all(value == 0xFF for value in full_slot[STORE_SLOT_OFFSET:STORE_SLOT_OFFSET + STORE_SIZE])
    if not store_erased or len(candidate_data) > STORE_SLOT_OFFSET:
        raise SystemExit("F300 overlaps or initializes lyoko_store")

    manifest.update({
        "schema": "openmitrastar.f300-emac-hw-demand-two-sample-from-f299/v1",
        "classification": "PRIVATE_DEVICE_BOUND_OFFLINE_HARDWARE_TEST_CANDIDATE",
        "candidate_eligible": True,
        "release_eligible": False,
        "flash_supported": True,
        "device_identity": source_manifest["device_identity"],
        "web_identity": source_manifest["web_identity"],
        "web_security": source_manifest["web_security"],
        "foundation_assets": assets_report,
        "native_qtn_control": source_manifest["native_qtn_control"],
        "native_rtl_control": source_manifest["native_rtl_control"],
        "config_apply": source_manifest["config_apply"],
        "transaction_hardening": source_manifest["transaction_hardening"],
        "dfs_observability": source_manifest["dfs_observability"],
        "network_observability": source_manifest["network_observability"],
        "hardware_provenance": source_manifest["hardware_provenance"],
        "package_catalog": source_manifest["package_catalog"],
        "package_runtime_fix": source_manifest["package_runtime_fix"],
        "opkg_compatibility": source_manifest["opkg_compatibility"],
        "led_control": source_manifest["led_control"],
        "config_store": source_manifest["config_store"],
        "transaction_review": source_manifest.get("transaction_review", {}),
        "package_web": source_manifest.get("package_web", {}),
        "hardware_inventory": source_manifest["hardware_inventory"],
        "developer_console": {**source_manifest["developer_console"], "firmware_line": "F300 Full"},
        "qtn_material_trial": source_manifest.get("qtn_material_trial", {}),
        "spi_probe": source_manifest["spi_probe"],
        "source": {
            "firmware": "F299 exact physically tested artifact, reconstructed offline from its pinned source lineage",
            "driver": str(BASE_DRIVER.relative_to(ROOT)).replace("\\", "/"),
            "f299_manifest_sha256": sha256(source / "manifest.json"),
            "f299_physical_evidence": "outputs/campaign/f299-flash-test-20260904T093250Z",
            "installed_after_f299_campaign": "F292 restored by the guarded rollback",
        },
        "hypothesis": {
            "claim": "Two consecutive 250 ms MAC-progress samples are sufficient evidence of real ingress when Linux RX is already idle, cur_rx is unchanged, the head descriptor is DMA-owned and no RX DMA IRQ is pending; reducing four samples to two should advance recovery while retaining every F299 safety gate and the F290 fallback.",
            "evidence": {
                "f299_run2_fault": "NO_RX_DESC (0x20)",
                "f299_run2_trigger_pokes": 13,
                "f299_run2_idle_ms": 5390,
                "f299_run2_head_status": "0x80000000",
                "f299_run2_mac_rx_delta": 3,
                "f299_run2_mac_rx_progress_streak": 4,
                "f299_run2_mac_rx_read_failures": 0,
                "expected_trigger_pokes_for_same_sequence": 11,
                "f291_constraint": "never suppress the unconditional F290 16-poke fallback",
            },
        },
        "change_scope": {
            "single_functional_variable": "reduce the F299 hardware-ingress confirmation threshold from four consecutive samples to two",
            "early_gate": {
                "linux_rx_idle_min_ms": 2000,
                "stall_sample_interval_ms": 250,
                "same_cur_rx_samples": EARLY_RESTART_SAMPLES,
                "mac_frames_rx_total_progress_samples": EARLY_RESTART_SAMPLES,
                "head_descriptor": "DMA-owned",
                "pending_dma_irq": "none",
                "fallback_boundary": "early path is disabled once the original 16-poke threshold is reached",
            },
            "fallback_restart_pokes": "unchanged at 16 and independent of hardware-counter validity",
            "restart_cooldown_ms": "unchanged at 10000",
            "restart_sequence": "byte-source-equivalent qtn_emac_restart_rx_dma call and post-restart timing sequence",
            "rx_ring": "unchanged at 256 descriptors",
            "napi_weight": "unchanged at 256",
            "tx_ring": "unchanged at 64 descriptors",
            "rx_buffer_size": "unchanged at 2048 bytes",
            "rootfs": "F299 rootfs with release identity updated only",
            "dtb": "byte-identical to F299",
            "radio5": "all Quantenna modules, firmware, scripts and configuration byte-identical to F299",
        },
        "binary_contract": binary_contract,
        "physical_validation": {
            "status": "NOT_RUN",
            "improvement_claimed": False,
            "required": "three matched 2.4 GHz runs, no management loss, fallback observation, 5 GHz sanity and rollback on regression",
        },
        "storage": {
            **source_manifest["storage"],
            "store_erased_ff": store_erased,
            "candidate_ends_before_store": len(candidate_data) <= STORE_SLOT_OFFSET,
        },
        "safety": {
            "normal_write_target": "mtd4/linux_live only after a separate authorized physical gate",
            "protected_partitions": "mtd0/mtd1/mtd2/mtd3/mtd5 unchanged",
            "mtd6": "logical rootfs view; never a physical write target",
            "hardware_actions": "none; offline build only",
        },
    })
    manifest["layout"]["mtd_mapping"] = source_manifest["layout"]["mtd_mapping"]
    manifest["contracts"]["hardware_boot"] = "NOT_RUN"
    manifest["contracts"]["flash"] = False
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="ascii")
    sums = sorted(path for path in output.iterdir() if path.is_file() and path.name != "SHA256SUMS")
    (output / "SHA256SUMS").write_text(
        "".join(f"{sha256(path)}  {path.name}\n" for path in sums), encoding="ascii"
    )

    final_out.parent.mkdir(parents=True, exist_ok=True)
    f293.restrict_acl(final_out.parent, directory=True)
    shutil.copytree(output, final_out)
    (final_out / "known_hosts.f300").write_text(
        f"192.168.1.90 {public_key}\n", encoding="ascii", newline="\n"
    )
    f293.restrict_acl(final_out, directory=True)
    for path in final_out.iterdir():
        if path.is_file():
            f293.restrict_acl(path, directory=False)
    print(json.dumps({
        "status": "PASS",
        "classification": manifest["classification"],
        "output": str(final_out),
        "candidate": str(final_out / manifest["artifacts"]["webformat"]["file"]),
        "bytes": manifest["artifacts"]["webformat"]["bytes"],
        "sha256": manifest["artifacts"]["webformat"]["sha256"],
        "single_variable": manifest["change_scope"]["single_functional_variable"],
        "hardware_actions": {"router": False, "uart": False, "ssh": False, "tftp": False, "flash": False},
    }, indent=2))
    cleanup()
    atexit.unregister(cleanup)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
