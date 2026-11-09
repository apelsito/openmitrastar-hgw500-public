# F372 normal 5 GHz AuC TQE observation image — 2026-10-21

Later utility probe: the device's `head -n` and `tail -n` work. The explanation
that F371 repaired their absence was incorrect. F372's inherited helpers are a
tested compatibility substitution, not a demonstrated fix for missing line
utilities. Its substantive new purpose remains F370 measurement. No image,
manifest, module or packaging evidence was replaced by this clarification.
Live evidence: `outputs/rea/arc700-20261021-r2/runtime-utility-probe-20261021T194330Z`.

F372 is an offline qualified full-image measurement candidate on exact F371.
It preserves the normal non-DFS starter compatibility and replaces only QDRV
with the complete F370 observation module, plus its required hash/identity
metadata. No physical installation, radio execution or performance gain is
claimed.

## Immutable image and lineage

- Private directory: `/workspace/user-home/.openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f372-f371-auc-tqe-observation-device-bound`.
- Image: `openmitrastar-linux510-f372-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH.webformat.bin`.
- Image SHA-256: `e8f7315c286e98d73f6bf4152c652f4633c8f63bd4a72b8a300e6859af619ef9`.
- Image size: **5,382,144 bytes**.
- Manifest SHA-256: `e4d9502d90fcb64c289c8369c41231a9dd837e05d2133e13953d3482b6abe0b5`.
- Build ID: `779bb20c0021b56e`.
- Product version: `lyoko-foundation-6.12.3-f372-auc-tqe-observation-device`.
- Result: `/workspace/user-home/.openmitrastar/devices/hgw500bna-qcv2-a2-primary/analysis/f372-fullimage-20261021T193818Z/result.json`.
- Physical prefix CRC32: `7b60a3c8`; full-slot read-only checksum model CRC32:
  `9a81d387`, SHA-256 `a3e55d331a721f22e107d57692c17ee102e80df0db0c3ca91421ea2f27d82f1f`.

The exact parent F371 is documented in
[F371 compatibility](OPENMITRASTAR_F371_NORMAL_START_COMPAT.md). Its image is
`b2eb2d0af57b6beaf47981d575ffd769997135fd46179bed8cb4fc3bd00ae147`.
This private image contains device identity and remains local. Full-slot data
is a checksum model, not a flash file and not an instruction to write store data.

## Exact delta

Only six regular files differ from F371:

1. `lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio5g/qdrv.ko`:
   exact F370, **686,144 bytes**, SHA-256
   `d5e1f58303eaaa02123e0cf6352bd40c40df3027be300d2a1143b07f54a05dae`.
2. `usr/sbin/om-radio5-start`: its one literal QDRV SHA-256 in the existing
   beacon-lifetime profile changes; replacing it back reproduces exact F371.
3. `usr/share/openmitrastar/radio5g/driver-contract.env`: its QDRV SHA-256 only.
4. `etc/openmitrastar/release`: candidate identity.
5. `usr/share/openmitrastar/radio5g/artifacts.sha256`: required hashes.
6. `usr/share/openmitrastar/storage/artifacts.sha256`: required catalog hash.

F371 PATH/head/tail helpers, starter logic, S55 init/feature, WLAN and all other
rootfs entries retain content, modes, owners and topology. Kernel/config/DT,
2.4 GHz, Ethernet, PSK handling, identity, calibration, regulatory settings,
F355 pin, queue ownership/return, existing TX BA policy and disabled thermal
sensor remain unchanged. No F367 native DFS or diagnostic image components are
introduced.

QDRV adds these four saturating uint parameters, permissions **0444**:

- `openmitrastar_auc_raw_ok`.
- `openmitrastar_auc_raw_other`.
- `openmitrastar_auc_busy_free`.
- `openmitrastar_auc_return_success`.

They observe the existing AuC `tqe_tx` result and return/free paths. They add no
per-packet logging or allocation and preserve packet/node ownership and return
behavior. Values are approximate under concurrent calls. Raw OK means consumed,
not RF delivered; counters after `tqe_tx` cannot observe a call stuck inside its
active hardware wait. This is measurement preparation, not a throughput fix.

## Offline evidence

The complete module qualification is
`outputs/rea/arc700-20261021-r2/f370-module-20261021T221200Z-r2/qualification-20261021T222300Z/result.json`,
SHA-256 `149f8f10743aa82907a82615d9adb9e5c23f1d6c61661a33b6dc7e44e3ee7ad2`.
Its status is `PASS_OFFLINE_COMPLETE_MODULE`: two candidate modules are byte
identical, 369 imports and 15 exports retain the F365 contract, and all four
added parameters are read only. Full baseline reconstruction checks 831
functions, 312,852 allocated code bytes, 14,034 canonical relocations and 1,932
symbols. The rebuilt baseline matches operational bytes/semantics; build
metadata is separately checked. This is ET_REL evidence before physical runtime
relocations, not hardware acceptance.

`tools/build_f372_observation_image.py` verifies the exact module receipt,
complete reconstruction and 225 unchanged source pins, then reuses F371 kernel
assets with the existing F164 compositor. `tools/f372_rootfs_worker.py` applies
and reversibly checks the bounded hash changes, verifies complete catalogs,
repackages SquashFS and independently extracts every entry. Both independent
full images match; Bootbase **PASS**, physical prefix fit **PASS**, rootfs
headroom **778,240 bytes**. No complete source release rebuild is claimed.

A separate immutable addendum at
`outputs/rea/arc700-20261021-r2/f372-packaging-verification-20261021T194000Z/result.json`
has `PASS_EXACT_PACKAGED_MODULE_AND_METADATA`. It extracts QDRV directly from
the produced rootfs, matches every `.modinfo` value to the qualified metadata,
checks the four 0444 uint permissions, and verifies exact module/starter/contract
catalog and runtime bindings. Module metadata evidence SHA-256 is
`29b37079e8a15e4c51424eb972cb6f9206bf393461078cc471277d93c9425a0d`.
The firmware and manifest were not modified by this independent addendum.

REA execution against a linked analysis-only derivation of the exact F370 QDRV
is preserved at `outputs/rea/arc700-20261021-r2/f370-full-rea-auc/rea.json`,
evidence `ev_1f36920fa41a73614b67429b0cff0016203af6857eedce123c77d773fefcb9f7`.
The immutable provenance addendum is
`outputs/rea/arc700-20261021-r2/f372-rea-provenance-20261021T194100Z/result.json`.
It binds the packaged QDRV, derived target, execution receipt and REA output.
Derived target SHA-256 is
`e228a671ce4286a8f937f6ce9d38c7d0180eb2b70a91669422a693378b475036`;
it contains synthetic external addresses and must never be loaded or packaged.
Ghidra reports overlapping globals and partial callee coverage. Static counter
paths do not establish physical behavior or performance.

The inherited F364 module-closure entries and F365 normal-start descriptors in
the F372 manifest provide baseline lineage only. The active candidate QDRV is
the separately qualified F370 artifact above. The addendum also resolves the
manifest's relative qualification reference to its canonical absolute path;
immutable image/manifest bytes remain unchanged.

## Physical status and next discriminator

**OFFLINE GO; physical NO_GO pending exact artifact authority and fresh device,
protection, readback and rollback gates.** All F372 physical gates remain UNRUN:
persistent cold boot, SSH/Ethernet/2.4 GHz preservation, 5 GHz control plane,
real-client visibility and AUTH/ASSOC/AUTHORIZED, useful bidirectional traffic,
reconnection/soak, manual preserved `mtd3` recovery and final release acceptance.

The measurement goal is to correlate these counters with real client transfers
and existing AuC/HBM/EMAC/GSO telemetry before changing ownership or aggregation
policy. Existing F365 RAM startup results do not establish F372 boot or traffic.
F355 still forbids safe hot replacement after radio mutation; a qualified full
image iteration and fresh boot remain separate physical actions.

Exact F365 rollback artifact is preserved, SHA-256
`43f4655f09eb01d749ca24c003689470b2f7c2d2738333297348e965e56d5355`,
full-slot CRC32 `118901d4` with the unchanged store. This artifact binding does
not replace fresh physical rollback checks. Normal writes target only physical
`mtd4/linux_live`; protected `mtd0`, `mtd1`, `mtd2`, `mtd3`, `mtd5` and logical
`mtd6/rootfs_live` remain outside normal writes. No device/network/UART access,
runtime mutation, reboot, TFTP or firmware write was performed. The legacy
fixed-path objective audit was not run or replaced.
