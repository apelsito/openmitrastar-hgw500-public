#!/bin/sh

# Re-encode the exact, verified Q1 kernel+initramfs payload using the same
# LZMA-alone format and 32 MiB dictionary used by the OEM Quantenna pipeline.
# This is offline only: it never contacts hardware, stages TFTP or writes flash.
set +x
set -eu

workspace=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
source_build="$workspace/work/mission-state/q1-full-product/build"
source_base=openmitrastar-linux510-q1-full-product-v1-RAM-ONLY
source_uimage="$source_build/$source_base.uImage"
source_web="$source_build/$source_base.webformat.bin"
source_manifest="$source_build/manifest.json"
source_rootfs_manifest="$workspace/work/mission-state/q1-full-product/rootfs-build/manifest.json"
template="$workspace/Firmware_para_HGW-500BNA-QCv2_ES_s00.00_g001_100WNU0b24_mitrastar_webformat.bin"
legacy_lzma="$workspace/work/volatile-loader/build/Quantenna-GPL/host/utilities/lzma"
make_uimage="$workspace/tools/make_q1_lzma_uimage.py"
pack="$workspace/tools/pack_topaz_webformat.py"
contract_tool="$workspace/tools/bootbase_contract_emulator.py"
lane="$workspace/work/mission-state/q1-lzma-flash-candidate"
build="$lane/build"
base=openmitrastar-linux510-q1-full-product-v1-LZMA-OFFLINE-NO-FLASH
raw="$build/$base.decompressed.bin"
lzma_a="$build/$base-a.lzma"
lzma_b="$build/$base-b.lzma"
uimage_a="$build/$base-a.uImage"
uimage_b="$build/$base-b.uImage"
web_a="$build/$base-a.webformat.bin"
web_b="$build/$base-b.webformat.bin"
uimage="$build/$base.uImage"
web="$build/$base.webformat.bin"
tftp="$workspace/work/tftp/omvl/linux510-q1-full-product-v1-LZMA-RAM-TEST-NO-FLASH.bin"

expected_source_uimage=fb2fab1fb54b141ae1ba7e7a977437ed9e6cdded8d0131405249b570adde5887
expected_source_web=7a5ab53db4055fcbe0e9b55b300430fe669d461ca237469165f556fbaf1107ac
expected_lzma_tool=04875199aab45068a183eededd351eb5abe4b39dfa6229c980e3e6e9f8d9ed18
slot_bytes=7995392
staging_start=0x83000000
ddr_end=0x88000000

sha() { sha256sum "$1" | awk '{print $1}'; }
require_sha() {
	actual=$(sha "$1")
	[ "$actual" = "$2" ] || {
		printf 'Q1 LZMA input drift: %s expected=%s actual=%s\n' "$1" "$2" "$actual" >&2
		exit 3
	}
}

for required in "$source_uimage" "$source_web" "$source_manifest" \
	"$source_rootfs_manifest" "$template" "$legacy_lzma" "$make_uimage" \
	"$pack" "$contract_tool"; do
	[ -f "$required" ] || { echo "missing Q1 LZMA input: $required" >&2; exit 3; }
done
require_sha "$source_uimage" "$expected_source_uimage"
require_sha "$source_web" "$expected_source_web"
require_sha "$legacy_lzma" "$expected_lzma_tool"

rm -rf -- "$build"
mkdir -p "$build"

# The source is a normal legacy uImage: its exact kernel+initramfs byte stream
# begins after the 64-byte header. No relink/rebuild or feature removal occurs.
dd if="$source_uimage" of="$raw" bs=64 skip=1 status=none
"$legacy_lzma" --keep --best "$raw" -c >"$lzma_a"
"$legacy_lzma" --keep --best "$raw" -c >"$lzma_b"
cmp -s "$lzma_a" "$lzma_b" || { echo 'Q1 LZMA encoder reproducibility mismatch' >&2; exit 5; }

python3 "$make_uimage" "$source_uimage" "$lzma_a" "$uimage_a"
python3 "$make_uimage" "$source_uimage" "$lzma_b" "$uimage_b"
cmp -s "$uimage_a" "$uimage_b" || { echo 'Q1 LZMA uImage reproducibility mismatch' >&2; exit 5; }

python3 "$pack" "$uimage_a" "$template" "$web_a" >/dev/null
python3 "$pack" "$uimage_b" "$template" "$web_b" >/dev/null
cmp -s "$web_a" "$web_b" || { echo 'Q1 LZMA RAS reproducibility mismatch' >&2; exit 5; }

cp "$lzma_a" "$build/$base.lzma"
cp "$uimage_a" "$uimage"
cp "$web_a" "$web"
mkdir -p "$(dirname "$tftp")"
cp "$web" "$tftp"
mkimage -l "$uimage" >"$build/$base.mkimage.txt"

python3 - "$contract_tool" "$web" "$build/bootbase-contract.json" <<'PY'
import importlib.util, json, pathlib, sys
tool, image, output = map(pathlib.Path, sys.argv[1:])
spec = importlib.util.spec_from_file_location("bootbase_contract", tool)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
result = module.validate_bootbase_slot(
    "q1-full-product-lzma-offline", image.read_bytes(),
    module.PARTITIONS["linux_live"][1],
)
report = module.image_to_dict(result)
report["candidate_eligible"] = False
report["scope_note"] = "format/CRC/LZMA round-trip/slot guard only; exact-image RAM boot pending"
output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
if not result.accepted_by_contract:
    raise SystemExit("Q1 LZMA candidate rejected by Bootbase contract")
PY

python3 - "$source_uimage" "$source_web" "$source_manifest" \
	"$source_rootfs_manifest" "$template" "$legacy_lzma" "$raw" \
	"$build/$base.lzma" "$uimage" "$web" "$tftp" "$build/bootbase-contract.json" \
	"$build/manifest.json" "$build/ram-layout.json" "$slot_bytes" \
	"$staging_start" "$ddr_end" <<'PY'
import hashlib, json, lzma, pathlib, struct, sys

(source_uimage, source_web, source_manifest, source_rootfs_manifest, template,
 lzma_tool, raw_path, lzma_path, uimage_path, web_path, tftp_path,
 contract_path, manifest_path, layout_path) = map(pathlib.Path, sys.argv[1:15])
slot = int(sys.argv[15])
staging_start = int(sys.argv[16], 0)
ddr_end = int(sys.argv[17], 0)

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def info(path):
    return {"file": path.name, "bytes": path.stat().st_size, "sha256": digest(path)}

source = source_uimage.read_bytes()
src = struct.unpack(">7I4B32s", source[:64])
raw = raw_path.read_bytes()
encoded = lzma_path.read_bytes()
uimage = uimage_path.read_bytes()
out = struct.unpack(">7I4B32s", uimage[:64])
web = web_path.read_bytes()
contract = json.loads(contract_path.read_text(encoding="utf-8"))
source_meta = json.loads(source_manifest.read_text(encoding="utf-8"))
rootfs_meta = json.loads(source_rootfs_manifest.read_text(encoding="utf-8"))

if source[64:] != raw or lzma.decompress(encoded, format=lzma.FORMAT_ALONE) != raw:
    raise SystemExit("Q1 LZMA exact decompressed payload binding failed")
if (out[4], out[5]) != (src[4], src[5]) or out[10] != 3:
    raise SystemExit("Q1 LZMA load/entry/compression header mismatch")
if web[64:0x2000] != template.read_bytes()[64:0x2000]:
    raise SystemExit("Q1 LZMA OEM RAS metadata drift")
if tftp_path.read_bytes() != web:
    raise SystemExit("Q1 LZMA TFTP copy differs from candidate")
if not contract["accepted_by_contract"] or web_path.stat().st_size > slot:
    raise SystemExit("Q1 LZMA candidate does not fit/validate as linux_live")

load_start = out[4]
load_end = load_start + len(raw)
entry = out[5]
staging_end = staging_start + len(web)
# Quantenna U-Boot LzmaTools.c places 16-bit probability entries after the
# output, at ((load_end + 0x80) & ~0x7f). Properties 0x5d mean lc=3/lp=0.
props = encoded[0]
lc = props % 9
rest = props // 9
lp = rest % 5
pb = rest // 5
probability_bytes = (1846 + (768 << (lc + lp))) * 2
probability_start = (load_end + 0x80) & ~0x7f
probability_end = probability_start + probability_bytes
safe = (
    staging_end < load_start
    and load_start <= entry < load_end
    and probability_start >= load_end
    and probability_end < ddr_end
)
layout = {
    "schema": "openmitrastar.q1-lzma-ram-layout/v1",
    "staging": {"start": f"0x{staging_start:08x}", "end": f"0x{staging_end:08x}"},
    "decompressed_image": {
        "start": f"0x{load_start:08x}", "end": f"0x{load_end:08x}",
        "bytes": len(raw), "entry": f"0x{entry:08x}",
    },
    "lzma_probability_workspace": {
        "start": f"0x{probability_start:08x}",
        "end": f"0x{probability_end:08x}", "bytes": probability_bytes,
        "lc": lc, "lp": lp, "pb": pb,
    },
    "ddr_end": f"0x{ddr_end:08x}",
    "staging_decompression_disjoint": staging_end < load_start,
    "entry_inside_decompressed_image": load_start <= entry < load_end,
    "probability_workspace_inside_ddr": probability_end < ddr_end,
    "safe_offline": safe,
}
if not safe:
    raise SystemExit("Q1 LZMA decompression/staging memory layout is unsafe")
layout_path.write_text(json.dumps(layout, indent=2, sort_keys=True) + "\n", encoding="utf-8")

manifest = {
    "schema": "openmitrastar.q1-lzma-flash-sized-candidate/v1",
    "classification": "FLASH-SIZED-Q1-LZMA-CANDIDATE-HARDWARE-PENDING-NO-FLASH",
    "candidate_eligible": False,
    "flash_supported": False,
    "hardware_actions": False,
    "network_actions": False,
    "profile": "Q1_FULL_PRODUCT",
    "scope": "OEM-PARITY-INTEGRATION",
    "private_build": False,
    "source": {
        "q1_manifest_sha256": digest(source_manifest),
        "q1_rootfs_manifest_sha256": digest(source_rootfs_manifest),
        "uncompressed_uimage": info(source_uimage),
        "overslot_webformat": info(source_web),
        "exact_decompressed_payload": info(raw_path),
    },
    "components": rootfs_meta["components"],
    "capabilities": source_meta["capabilities"],
    "source_rootfs": rootfs_meta["rootfs"],
    "artifacts": {
        "lzma_payload": info(lzma_path), "uimage": info(uimage_path),
        "webformat": info(web_path), "bootbase_contract": info(contract_path),
        "ram_layout": info(layout_path), "tftp_copy": info(tftp_path),
    },
    "compression": {
        "format": "lzma-alone", "uimage_id": 3,
        "properties": encoded[:5].hex(),
        "declared_uncompressed_bytes": int.from_bytes(encoded[5:13], "little"),
        "decoded_bytes": len(raw), "decoded_sha256": digest(raw_path),
        "legacy_encoder_sha256": digest(lzma_tool),
        "two_encodes_identical": True,
    },
    "header": {
        "load": f"0x{out[4]:08x}", "entry": f"0x{out[5]:08x}",
        "load_entry_preserved_from_q1": (out[4], out[5]) == (src[4], src[5]),
        "oem_arc_arch": out[8], "compression": out[10],
    },
    "slot": {
        "name": "linux_live", "bytes": slot,
        "candidate_bytes": len(web), "spare_bytes": slot - len(web),
        "fits": len(web) <= slot, "bootbase_contract": "pass_offline",
    },
    "ram_layout": layout,
    "reproducibility": {
        "two_lzma_encodes_identical": True,
        "two_uimages_identical": True, "two_webformat_images_identical": True,
    },
    "kernel_integration_gates": source_meta["kernel_integration_gates"],
    "security": source_meta["security"],
    "completion_claims": source_meta["completion_claims"],
    "runtime_gates": {
        "exact_candidate_ram_boot": "pending",
        "decompression_uart_evidence": "pending",
        "radio2g_association_traffic_soak": "pending",
        "radio5g_association_traffic_soak": "pending",
        "flash": "forbidden-until-exact-image-ram-equivalence-and-readback-gates",
    },
    "ram_boot_contract": {
        "classification": "RAM-ONLY-EXACT-CANDIDATE-TEST",
        "tftp_root": "work/tftp/omvl",
        "file": tftp_path.name,
        "sha256": digest(tftp_path),
        "staging_address": "0x83000000",
        "commands": [
            f"tftpboot 0x83000000 {tftp_path.name}",
            "bootm 0x83000000",
        ],
        "expected_bootbase_marker": "Uncompressing Kernel Image ... OK",
        "flash_write": False,
    },
}
manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY

sha256sum "$raw" "$build/$base.lzma" "$uimage" "$web" "$tftp" \
	"$build/bootbase-contract.json" "$build/ram-layout.json" "$build/manifest.json" \
	>"$build/SHA256SUMS"

python3 "$workspace/tools/test_q1_lzma_flash_candidate.py"
printf 'OMQ1_LZMA_FLASH_SIZED_BUILD_PASS sha256=%s bytes=%s spare=%s decoded_sha256=%s flash=0 hardware=0\n' \
	"$(sha "$web")" "$(wc -c <"$web")" "$((slot_bytes - $(wc -c <"$web")))" "$(sha "$raw")"
