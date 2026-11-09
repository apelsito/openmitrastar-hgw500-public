# OpenMitraStar F266 Full candidate

## Identity

- Runtime: `lyoko-foundation-6.0.3-f266-full-device`
- Bytes: `5251072`
- SHA-256: `682b6d3d55039356b5e67d1bd14df32380b5112e4c6ea2583174d16b1c44b9df`
- Full-slot CRC32: `8e8edc4d`
- Full-slot SHA-256: `90ecb99c4f57e549b42fb63fdfff9888f8f3c9ef1d052f1ba294491033b9985b`
- Bootbase contract: PASS
- Normal target: physical `mtd4/linux_live` only

## Why F266 exists

F265 successfully proved the complete product image, package lifecycle and the
Realtek channel/bandwidth transaction. Its subsequent Quantenna mutation made
the management datapath unavailable. F266 therefore keeps the 5 GHz AP boot
path unchanged but disables dynamic Quantenna mutation by default.

F266 also writes bounded `OMQTNCTL stage=...` markers to `/dev/kmsg` around:

- hostapd stop;
- RF enable;
- interface up;
- mode selection;
- SSID and channel writes;
- TX power setup;
- 802.11h/TPC setup;
- hostapd restart;
- post-hostapd RF rearm;
- final verified readback.

This lets the next isolated UART experiment identify the exact operation that
stops progress. The web still exposes every documented channel for inspection,
but 5 GHz mutations are unavailable until explicitly enabled for the lab.

## Validation

- Full source/emulator and integration suite: 42/42 PASS
- SHA256SUMS: PASS
- Kernel, Kconfig, DTB and radio modules: byte-identical to F265/F263
- Hardware boot: PASS on 2026-09-03
- Bootbase TFTP write/readback: PASS
- Platform gate: PASS
- F266 was superseded by installed F267 after proving the fail-closed Quantenna baseline.

## Next physical sequence

1. Power-cycle the currently unresponsive F265 installation.
2. Confirm F265 baseline through SSH without changing a radio.
3. Promote F266 through Bootbase TFTP to `mtd4`.
4. Verify platform, web and package manager.
5. Run the Realtek transaction independently.
6. Enable Quantenna mutation only for an UART-captured step-by-step trial.
