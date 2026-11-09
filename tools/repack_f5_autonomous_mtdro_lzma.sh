#!/bin/sh
set -eu

workspace=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
build="$workspace/work/mission-state/f5-autonomous-mtdro/build"
base=openmitrastar-linux510-f5-autonomous-mtdro-v1
legacy="$workspace/work/volatile-loader/build/Quantenna-GPL/host/utilities/lzma"
make_uimage="$workspace/tools/make_q1_lzma_uimage.py"
pack="$workspace/tools/pack_topaz_webformat.py"
template="$workspace/Firmware_para_HGW-500BNA-QCv2_ES_s00.00_g001_100WNU0b24_mitrastar_webformat.bin"
contract="$workspace/tools/bootbase_contract_emulator.py"

uimage="$build/$base.uImage"
raw="$build/$base.raw-payload.bin"
lzma_a="$build/$base-a.lzma"
lzma_b="$build/$base-b.lzma"
lzma_final="$build/$base.lzma"
lzma_uimage_a="$build/$base-a.lzma.uImage"
lzma_uimage_b="$build/$base-b.lzma.uImage"
lzma_uimage="$build/$base.lzma.uImage"
web_a="$build/$base-a.lzma.webformat.bin"
web_b="$build/$base-b.lzma.webformat.bin"
web="$build/$base.lzma.webformat.bin"

for required in "$legacy" "$make_uimage" "$pack" "$template" "$contract" "$uimage"; do
	[ -e "$required" ] || { echo "missing input: $required" >&2; exit 3; }
done

dd if="$uimage" of="$raw" bs=64 skip=1 status=none
"$legacy" --keep --best "$raw" -c >"$lzma_a"
"$legacy" --keep --best "$raw" -c >"$lzma_b"
cmp -s "$lzma_a" "$lzma_b" || { echo "F5 LZMA reproducibility mismatch" >&2; exit 4; }
python3 "$make_uimage" "$uimage" "$lzma_a" "$lzma_uimage_a"
python3 "$make_uimage" "$uimage" "$lzma_b" "$lzma_uimage_b"
cmp -s "$lzma_uimage_a" "$lzma_uimage_b" || { echo "F5 LZMA uImage reproducibility mismatch" >&2; exit 4; }
python3 "$pack" "$lzma_uimage_a" "$template" "$web_a" >/dev/null
python3 "$pack" "$lzma_uimage_b" "$template" "$web_b" >/dev/null
cmp -s "$web_a" "$web_b" || { echo "F5 LZMA webformat reproducibility mismatch" >&2; exit 4; }

cp "$lzma_a" "$lzma_final"
cp "$lzma_uimage_a" "$lzma_uimage"
cp "$web_a" "$web"

python3 - "$contract" "$web" "$build/bootbase-contract-lzma.json" <<'PY'
import importlib.util
import json
import pathlib
import sys

tool, image, output = map(pathlib.Path, sys.argv[1:])
spec = importlib.util.spec_from_file_location("bootbase_contract", tool)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
result = module.validate_bootbase_slot(
    "f5-autonomous-mtdro",
    image.read_bytes(),
    module.PARTITIONS["linux_live"][1],
)
report = module.image_to_dict(result)
report["candidate_eligible"] = False
report["scope_note"] = (
    "F5 autonomous management candidate; LZMA slot guard only; "
    "no hardware boot in this step"
)
output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
if not result.accepted_by_contract:
    raise SystemExit("LZMA Bootbase candidate contract rejected")
PY

sha256sum "$raw" "$lzma_final" "$lzma_uimage" "$web" >"$build/SHA256SUMS.lzma"
printf 'OMF5_AUTONOMOUS_LZMA_REPACK_PASS web_sha256=%s web_bytes=%s\n' \
	"$(sha256sum "$web" | cut -d' ' -f1)" "$(wc -c <"$web")"
