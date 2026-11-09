#!/usr/bin/env python3
import argparse
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "outputs" / "samsung-m5" / "pocs" / "node_swu_teec_ddr_init_stream_probe.S"
MSD = ROOT / "outputs" / "samsung-m5" / "M-KSU2SMWWC-extracted" / "M-KSU2SMWWC" / "image" / "upgrade.msd"
OUT_DIR = ROOT / "outputs" / "samsung-m5" / "msddecrypt"
POC_DIR = ROOT / "outputs" / "samsung-m5" / "pocs"


PARTS = {
    "ddr.init": (0x0000108E, 0x00019010, "9f4bfa3cda1c501b", 0x5B87AA9E),
    "seret.bin": (0x0001A09E, 0x002FE010, "1a46ebc10af8a0aa", 0x71EB9BAF),
    "uImage": (0x003180AE, 0x0064FAE0, "4f6de96577a64dfb", 0x82D813C6),
    "dtb.bin": (0x00967B8E, 0x0017E010, "49f3d5e78036889d", 0xE541517C),
    "sign.bin": (0x00AE5B9E, 0x00000410, "b7c00ef0769420dc", 0x906E4A8F),
    "secos_drv.bin": (0x00EE3FBE, 0x000FE010, "f68337e950e58223", 0x24832745),
    "factory_peq.img": (0x461B1FDE, 0x00040010, "c936d6696e908450", 0xC4B9A838),
}


def ident(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_").lower()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("partition", choices=sorted(PARTS))
    args = ap.parse_args()

    off, size, salt_hex, crc = PARTS[args.partition]
    name = ident(args.partition)
    salt_path = OUT_DIR / f"{name}_salt.bin"
    cipher_path = OUT_DIR / f"{name}_cipher.bin"
    source_path = POC_DIR / f"node_swu_teec_{name}_stream_probe.S"

    data = MSD.read_bytes()
    cipher = data[off : off + size]
    if len(cipher) != size:
        raise SystemExit(f"short read for {args.partition}: got {len(cipher)} expected {size}")

    salt_path.write_bytes(bytes.fromhex(salt_hex))
    cipher_path.write_bytes(cipher)

    source = TEMPLATE.read_text(encoding="ascii")
    source = source.replace(".equ TOTAL_SIZE, 102416", f".equ TOTAL_SIZE, {size}")
    source = source.replace('/tmp/ddr_init_cipher.bin', f'/tmp/{name}_cipher.bin')
    source = source.replace('/tmp/swu_ddr_init_plain.bin', f'/tmp/swu_{name}_plain.bin')
    source = source.replace('/tmp/swu_ddr_init_stream_status.bin', f'/tmp/swu_{name}_stream_status.bin')
    source = source.replace('outputs/samsung-m5/msddecrypt/ddr_init_salt.bin', f'outputs/samsung-m5/msddecrypt/{name}_salt.bin')
    source_path.write_text(source, encoding="ascii")

    print(f"partition={args.partition}")
    print(f"id={name}")
    print(f"offset=0x{off:08x}")
    print(f"size=0x{size:08x} ({size})")
    print(f"salt={salt_hex}")
    print(f"expected_crc32=0x{crc:08x}")
    print(f"salt_path={salt_path}")
    print(f"cipher_path={cipher_path}")
    print(f"source_path={source_path}")


if __name__ == "__main__":
    main()
