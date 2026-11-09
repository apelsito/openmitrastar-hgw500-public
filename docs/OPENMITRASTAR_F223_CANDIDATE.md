# OpenMitraStar F223 Candidate

Date: 2026-09-02

## Purpose

F223 is a private, device-bound EMAC experiment built from the installed F222
baseline. It tests whether increasing the direct-AHB RX ring from 128 to 256
descriptors removes intermittent `NO_RX_DESC` pressure without reducing 2.4 GHz
throughput or disturbing 5 GHz.

## Artifact

- File: `openmitrastar-linux510-f223-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH.webformat.bin`
- Bytes: `5206016`
- SHA-256: `a63ccce69776732269ac4c08f29062c74b93eda945c88778ab63efd9215be2bc`
- Full-slot CRC32: `d176a661`
- Full-slot SHA-256: `8f4c23877521e904e82b5d124b96a987882865b259e03cf8c8cdd84a6c357efa`
- Location: `%USERPROFILE%\.openmitrastar\devices\hgw500bna-qcv2-a2-primary\firmware\f223-device-bound`

## Single Variable

- EMAC RX ring: `128 -> 256` descriptors.
- NAPI weight: unchanged at `128`.
- RX buffer size: unchanged at `2048` bytes.
- TX ring: unchanged at `64` descriptors.
- Recovery policy: unchanged.
- F222 rootfs, kernel config and DTB: byte-identical.
- Quantenna, Realtek WLAN, bridge, TQE, package manager, web and SSH identity:
  unchanged.

The added nominal allocation is `265728` bytes before SKB allocator overhead.
The expected physical cost is below 400 KiB against the F222 live
`MemAvailable` value of approximately 22.9 MiB.

## Offline Evidence

- Bootbase contract: PASS.
- Slot fit: PASS.
- Rootfs magic and split layout: PASS.
- Binary RX descriptor region: `0x1000` bytes.
- Binary total descriptor allocation: `0x1400` bytes.
- Binary NAPI weight: `0x80` / 128.
- SHA256SUMS: PASS.
- Focused tests: 14 PASS.

An earlier F223 draft built from the old F164 base was rejected before flash
because it disabled multicast/IGMP and lost the `lyoko_store` DTB split. It is
preserved separately as rejected evidence and is not eligible for promotion.

## Physical Gate

1. Flash only physical `mtd4/linux_live`, erasing only the `0x5e0000` firmware
   prefix and preserving the `0x1c0000` store tail.
2. Verify boot, SSH identity, rootfs/store windows, both radio control planes,
   package lifecycle and zero fatal markers.
3. Verify the boot log reports descriptor allocation `tx=1024 rx=4096` and
   runtime telemetry reports NAPI weight 128.
4. Run three 32 MiB bidirectional 2.4 GHz transfers from the Windows client.
5. Require zero RX restarts, near-zero `NO_RX_DESC`, zero allocation failures,
   zero WLAN errors/drops and no throughput regression against F219/F222.
6. Only a passing result proceeds to simultaneous dual-radio soak.

F223 currently has hardware status `NOT_RUN`; no performance improvement is
claimed yet.
