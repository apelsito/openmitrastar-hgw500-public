"""Versioned offline F368r2 qdrv wrapper; preserves the F368 builder unchanged."""
import hashlib
import json
from pathlib import Path
import sys

import build_f368_qdrv_module as builder


def main():
    builder.SOURCE = builder.ROOT / "work/kernel-port/f368r2-txpower-quarantine/qdrv/qdrv"
    rc = builder.main()
    position = sys.argv.index("--output")
    output = Path(sys.argv[position + 1])
    result_path = output / "result.json"
    result = json.loads(result_path.read_text())
    result["schema"] = "openmitrastar.f368r2-qdrv-module/v1"
    result["source_revision"] = "F368r2"
    result["source_parent"] = "F368"
    result["baseline_symbol_contract"] = "F367r9"
    result["promotion"] = "NO_GO_PHYSICAL"
    result["change"] = "Only STORE38 retains a descriptor after published timeout; deadlines, other producers and lifetime pin unchanged."
    result["builder_pins"] = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in (Path(__file__), Path(builder.__file__), Path(builder.context.__file__))}
    result_path.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({key: value for key, value in result.items() if key not in ("source_pins", "builder_pins")}))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
