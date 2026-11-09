# OpenMitraStar F180 storage probe

Date: `2026-09-01`

F180 is the first firmware candidate that represents the proposed storage
split in the device tree while keeping every flash view read-only.

Logical Linux MTD order:

```text
mtd0 uboot_env       0x010000
mtd1 uboot_env_bak   0x010000
mtd2 data            0x080000
mtd3 rootfs_live     0x460000
mtd4 lyoko_store     0x1c0000
```

`root=31:3` remains unchanged. `lyoko_store` is not mounted, formatted, erased
or written. Its only purpose in F180 is to prove that the physical boundaries,
MTD numbering and persistent boot remain correct.

F180 uses the F179 NAPI/package-manager product and changes only its release
identity and DTS layout. Physical validation remains `NOT_RUN`.

Build:

```powershell
.\tools\build_f180_storage_probe.ps1
```

## Built artifact

- Candidate:
  `work/mission-state/q3-persistent-composite-f180-storage-readonly-probe/build/openmitrastar-linux510-q3-persistent-f180-storage-readonly-probe-LZMA-OFFLINE-NO-FLASH.webformat.bin`
- Size: `5,107,712` bytes
- SHA-256: `20cac97488420d6033d028e098a9ad98b8ac1bcb7031863e4146c2770e5cca9b`
- Candidate CRC32: `f49049f4`
- Full-slot CRC32: `0d991cdb`
- Full-slot SHA-256:
  `ec08a273d93983a63e895caba545fc412b5f556bbd23159c944cc9d47d532e37`
- Kernel LZMA SHA-256:
  `ab82dcbd489238e4fa721151196f20fec62d4cb1535c14483b401cfc712cb9ee`
- Rootfs SHA-256:
  `a5d20a38bee4186f731c16f3ffcfba48113e0ab08abf9bc61251e2cea7861127`
- Offline tests: `12 passed`
- Repeated build SHA-256 and `SHA256SUMS`: PASS
- Canonical non-storage DTS restored after each build: PASS

The future hardware gate is strictly read-only and requires `mtd3` rootfs,
`mtd4` store, no store mount and a readable store hash without issuing writes.
