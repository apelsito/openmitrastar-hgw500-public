# F369 STORE38 diagnostic image — 2026-10-21

F369 is an **offline qualified diagnostic candidate** for the physical
HGW-500BNA-QCv2 A2. No router, UART, Ethernet, runtime or firmware operation was
performed by its image builder. It has not been installed or accepted physically.

## Immutable artifact

The image and manifest are private, because the inherited rootfs includes the
device identity. They must not be published or copied into public release assets.

- Image directory: `/workspace/user-home/.openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f369-f367r9-store38-quarantine-device-bound`.
- Image: `openmitrastar-linux510-f369-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH.webformat.bin`.
- Image SHA-256: `d803af79949e4d0bb26791c8f234976f66a2934d724c01ed4b4d0486f067250e`.
- Image size: **5,468,160 bytes**.
- Manifest SHA-256: `514ce7f941531d80644a86139d952658f777f545cfba276665d1fb9910bb7814`.
- Build ID: `29f5af3ccc617483`.
- Product version: `lyoko-foundation-6.12.0-f369-store38-quarantine-device`.
- Result: `/workspace/user-home/.openmitrastar/devices/hgw500bna-qcv2-a2-primary/analysis/f369-fullimage-20261021T191849Z/result.json`.
- Firmware prefix padded to `0x5e0000` CRC32: `20e74b8c`.
- Full-slot **checksum model only**, incorporating the existing store: CRC32
  `f0df1459`, SHA-256 `900abd998fe5f01e493da5334845c1e2c95e52c167ba83d3538bf0ad35f0896b`.
  This is not a generated flash file or permission to write store content.

## Exact parent and change

The exact parent is private F367r9, SHA-256
`6bf5a08edd5b18adf1597efbd5367d5ad439363c7f7a13a035efc615b4cee440`,
5,468,160 bytes; parent manifest SHA-256
`eff3e150b7c9a03d1cac95fe3ffae3fff374180ce0ff58215acf9ff230181858`.

Its QDRV is replaced with exact F368r2,
`01402519e44293b2311c395edf5ae9f56c77a076780669a3b9179fe9af25c240`,
703,624 bytes. Relative to F367r9, only two driver source bodies change:

1. `qdrv_hostlink_store_txpow` in `qdrv_hostlink.c` calls
   `qdrv_send_ioctl_owned(qw, ioctl, true, NULL, true)`. Command STORE38 has
   DONE/ERR acknowledgement normalization and keeps a published descriptor
   reserved on timeout. A late STORE38 response cannot acknowledge a subsequent
   TX-off operation reusing the same slot.
2. `qdrv_set_channel` in `qdrv_wlan.c` checks STORE38's normalized return,
   invokes the existing `qdrv_f367_channel_fault` path on failure, and returns
   before progressing the channel transition. The existing fault path remains
   responsible for the separate TX-off request and its own acknowledgement.

The descriptor is retained until reboot. Repeated STORE38 timeouts can exhaust
the ring; exhaustion is rejected by the existing allocation/fault path. This
candidate does not add safe module unload, descriptor reclamation, new timeouts,
automatic recovery, or automatic product 5 GHz startup.

Only these seven rootfs files change:

- `lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio5g/qdrv.ko`.
- `usr/libexec/openmitrastar/om-radio5-start-f367-native`: its ASCII QDRV hash only.
- `usr/share/openmitrastar/radio5g/driver-contract.env`: its QDRV hash only.
- `etc/openmitrastar/release`: candidate identity.
- `usr/share/openmitrastar/dfs-f367/profile.json`: candidate metadata.
- `usr/share/openmitrastar/radio5g/artifacts.sha256`.
- `usr/share/openmitrastar/storage/artifacts.sha256`.

The kernel, DTB, config, WLAN, 2.4 GHz modules, radio firmware, native radar
provider, radar engine, static regulatory helper, supervisor, controller/status
helpers, shell admission, regulatory configuration, watchdog and CAC/NOP/HEALTH
deadlines remain byte-identical to F367r9. Diagnostic activation constraints
remain in force.

## Offline evidence

`tools/build_f369_store38_image.py` reuses the existing F164 image composer and
the pinned parent kernel assets. `tools/f369_rootfs_worker.py` extracts and checks
the parent, applies the bounded delta, validates the catalogs and shell syntax,
packs SquashFS, then independently extracts and verifies every entry. Old
artifacts and builder sources are untouched. The Windows builder uses the
existing `REA-Linux` distribution for Linux SquashFS tooling.

- QDRV: two identical F368r2 builds; the F367r9 symbol contract remains
  393 imports and 15 exports.
- Replay: `outputs/rea/arc700-20261021-r2/f368r2-fault-path-r3/result.json`,
  **16 cases / 80 checks**, including stale DONE/ERR, genuine TX-off ACK,
  unpublished timeout and ring exhaustion.
- REA: `outputs/rea/arc700-20261021-r2/f368r2-rea-store38/result.json` and
  `rea.json`; analysis of the derived linked target confirms command 38 and the
  ACK/quarantine arguments. The target SHA-256 is
  `b1f0ebe3f75984c9f4115c90b5c5716c3a313a693a43c8ca09cd407f0687e6b2`.
  This analysis target has synthetic external functions and is not firmware.
- Source provenance: F368r2 module pins and the versioned source manifest,
  replay source pins, REA output, builder/composer inputs and exact parent
  inputs are included in the F369 manifest; 174 unique paths are checked again
  after composition.
- Full image: two independent SquashFS repacks and compositions match for all
  firmware/kernel/rootfs assets. Bootbase **PASS**, physical firmware prefix
  fit **PASS**, rootfs headroom **692,224 bytes**. No complete source release
  rebuild is claimed.

The controlled replay substitutes the ring, clocks and mailbox. REA provides
static analysis of a derived target. Neither proves physical ARC execution,
MuC timing, DMA coherency, RF silence, radio behavior or recovery.

The legacy objective audit was regenerated at 2026-10-21 19:20:15 UTC. Its
fixed historical output path `outputs/audit/lyoko-full-liberation-20260905.json`
was overwritten by that legacy runner; no exact earlier bytes were available
in the root Git tree or the local audit directory. A subsequent fresh run of
the same audit, with only the output path redirected, is preserved at
`outputs/audit/lyoko-full-liberation-20261021T192210Z.json`. Both audits cover
F314–F319 historical evidence. Their `installed_firmware=F319` field is explicitly
historical and **does not describe today's physical device or F369 acceptance**.
Use `docs/AGENT_CURRENT_MISSION.md` and the 2026-10-21 radio evidence for the
current F367r9 image and exact F365 module pair active in RAM. The legacy audit
also retains a recorded independent `mtd3` recovery NO_GO; this is not resolved
by F369 composition.

## Gates and recovery

**OFFLINE GO; physical NO_GO pending exact artifact authorization and current
hardware protection/readback/recovery gates.** No boot, control-plane, client,
bidirectional traffic, RF/CAC/NOP or release acceptance has been run for F369.

The inherited F365 recovery image remains exact SHA-256
`43f4655f09eb01d749ca24c003689470b2f7c2d2738333297348e965e56d5355`,
5,382,144 bytes, expected full-slot CRC32 `118901d4` with the preserved store.
This is existing artifact evidence, not current physical recovery verification.
The preserved store checksum remains SHA-256
`fcbeb5ab9f1fde273632a0f1a2f0a5d8b1304aa361439c24d1fe8e29cbb1c873`,
CRC32 `5d2ee646`; it is read only during composition.

Any future authorized installation targets only physical `mtd4/linux_live`.
Protected `mtd0`, `mtd1`, `mtd2`, `mtd3` and `mtd5` remain outside normal writes.
Logical `mtd6/rootfs_live` is never appended to a raw SPI image or treated as a
physical partition. Do not change boot environment while SSH is healthy. The
preserved manual rollback boundary is UART `ATGO` to `mtd3/linux_safety`, subject
to its applicable current gates. Building this candidate authorizes no physical
operation.
