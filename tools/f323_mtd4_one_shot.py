"""F323 UART writer entry: require the live inherited binding before hardware."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys

import f321_mtd4_one_shot as previous

UART_LOADER = Path(__file__).with_name("f323_uart_ymodem_load.py")

IMAGES = {
    "9d8dbd5bd9a6c372e95d8f6365396f8eb4695ab61848cd49341d76fee2153c11": "promote",
    "eb8e23ac75ec50e113cd337e9b68ab86e366a09c8dbbec255a3b426843a9da18": "rollback",
    "a0c7350a50e5e4b532a0202982e6cd3c2d3da4e2e91079cd105473b248523f11": "fallback",
}


def main() -> int:
    if any(arg.startswith("--") and arg.split("=", 1)[0] not in previous.OPTIONS for arg in sys.argv[1:]):
        raise SystemExit("unsupported F323 writer option")
    parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    parser.add_argument("--execute", action="store_true")
    args, _ = parser.parse_known_args()
    if args.execute:
        candidate = os.environ.get("OM_Q3_FLASH_EXPECTED_SHA256", "")
        if candidate not in IMAGES or not os.environ.get("OM_F323_PHYSICAL_CONTEXT"):
            raise SystemExit("F323 writer requires exact image and inherited physical binding")
        guard = Path(__file__).with_name("f323_assert_physical_context.ps1")
        result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
            "-File", str(guard), "-CandidateSha256", candidate, "-Direction", IMAGES[candidate]],
            capture_output=True, timeout=30, check=False)
        if result.returncode != 0 or result.stdout.decode("ascii", errors="replace").strip() != "PASS_F323_INHERITED_PHYSICAL_CONTEXT":
            raise SystemExit("F323 writer physical context was not verified")
    # Select the reviewed receiver-driven adapter for this process only; the
    # sealed F321 loader and all existing image/RAM-integrity checks stay intact.
    saved_loader = previous.UART_LOADER
    previous.UART_LOADER = UART_LOADER
    try:
        return previous.main()
    finally:
        previous.UART_LOADER = saved_loader


if __name__ == "__main__":
    raise SystemExit(main())
