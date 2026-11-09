#!/usr/bin/env python3
"""F321-only UART entry point; reuse the unchanged guarded F45 writer."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

import run_q3_f45_radio5_powerselect_nonfatal_openlab_autostart_mtd4_flash_one_shot as original


UART_LOADER = Path(__file__).with_name("f321_uart_ymodem_load.py")
OPTIONS = {
    "--execute", "--ack", "--port", "--client-ip", "--host", "--skip-reboot",
    "--timeout", "--erase-bytes", "--transport", "--uart-attach-topaz",
    "--evidence-dir", "--attempt-id", "--help",
}


def main() -> int:
    # Reject abbreviations so the original parser cannot reinterpret an
    # unchecked flag as execute, receiver-ready or another transport mode.
    if any(arg.startswith("--") and arg.split("=", 1)[0] not in OPTIONS for arg in sys.argv[1:]):
        raise SystemExit("F321 writer received an unsupported option")
    parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--transport", default="uart-ymodem")
    parser.add_argument("--skip-reboot", action="store_true")
    parser.add_argument("--uart-attach-topaz", action="store_true")
    args, _ = parser.parse_known_args()
    if args.transport != "uart-ymodem" or (args.execute and not (args.skip_reboot and args.uart_attach_topaz)):
        raise SystemExit("F321 writer requires UART attach after the separately guarded reboot")
    previous_loader, previous_argv = original.UART_LOADER, sys.argv
    original.UART_LOADER = UART_LOADER
    sys.argv = [*sys.argv, "--transport", "uart-ymodem"]
    try:
        return original.main()
    finally:
        original.UART_LOADER, sys.argv = previous_loader, previous_argv


if __name__ == "__main__":
    raise SystemExit(main())
