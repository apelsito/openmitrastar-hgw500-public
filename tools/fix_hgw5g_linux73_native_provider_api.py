"""Versioned Linux 7.3 native provider API migration; preserve prior candidates."""
import argparse
import hashlib
import json
import shutil
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--parent", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    shutil.copytree(args.parent, args.output)
    changes = {}

    rel = "source/platform/qtsens/temp_sensor.c"
    path = args.output / rel
    text = path.read_text()
    probe = "static int qtn_tsensor_probe(struct i2c_client *client,\n\t\t\t\t\t\t\tconst struct i2c_device_id *dev_id)"
    assert text.count(probe) == 1
    text = text.replace(probe, "static int qtn_tsensor_probe(struct i2c_client *client)", 1)
    remove = "static int qtn_tsensor_remove(struct i2c_client *client)"
    assert text.count(remove) == 1
    text = text.replace(remove, "static void qtn_tsensor_remove(struct i2c_client *client)", 1)
    body_start = text.index("static void qtn_tsensor_remove(")
    body_end = text.index("static const struct i2c_device_id", body_start)
    body = text[body_start:body_end]
    assert body.count("\treturn 0;\n") == 1
    text = text[:body_start] + body.replace("\treturn 0;\n", "", 1) + text[body_end:]
    path.write_text(text, newline="\n")
    changes[rel] = sha(path)

    rel = "source/platform/topaz/switch_tqe.c"
    path = args.output / rel
    text = path.read_text()
    napi = "netif_napi_add(dev, &priv->napi, &tqe_rx_napi_handler, 8);"
    assert text.count(napi) == 1
    text = text.replace(napi, "netif_napi_add_weight(dev, &priv->napi, &tqe_rx_napi_handler, 8);", 1)
    path.write_text(text, newline="\n")
    changes[rel] = sha(path)

    rel = "source/platform/ruby/mem_check.h"
    source = root / "work/linux510-radio-port/quantenna/platform/ruby/mem_check.h"
    shutil.copyfile(source, args.output / rel)
    changes[rel] = sha(args.output / rel)

    proof = json.loads((args.parent / "result.json").read_text())
    proof.update(
        status="SOURCE_ONLY_LINUX73_NATIVE_PROVIDER_API_PENDING_BUILD",
        parent=str(args.parent),
        changed_sources=changes,
        native_memory_header={"source": str(source), "sha256": sha(source)},
        native_provider_api_changes=[
            "I2C probe accepts client only; unused device-id argument removed",
            "I2C remove returns void; identical private-state free path retained",
            "TQE uses netif_napi_add_weight with original weight 8",
            "DMA imports original memory validation header instead of a stub",
        ],
        firmware_eligible=False,
    )
    proof["files"] = {
        str(path.relative_to(args.output)): sha(path)
        for group in ("source", "headers", "kernel-overlay", "providers")
        for path in (args.output / group).rglob("*") if path.is_file()
    }
    (args.output / "result.json").write_text(json.dumps(proof, indent=2) + "\n")
    print(json.dumps({"status": proof["status"], "changed_sources": changes}, indent=2))


if __name__ == "__main__":
    main()
