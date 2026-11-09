# F371 normal 5 GHz startup compatibility — 2026-10-21

Later live verification changes the rationale: `/bin/head -n` and `/bin/tail -n`
both succeed on the current device. The earlier claim of absent line applets
was incorrect; only `head -c` fails. Evidence:
`outputs/rea/arc700-20261021-r2/runtime-utility-probe-20261021T194330Z`.
This image remains byte-coherent offline, but its helper substitution is not
proven necessary for the current firmware. Do not use that discarded rationale
as evidence that F371 will repair automatic startup or justify installing it.
The sealed image and manifest remain unchanged.

F371 is an offline qualified compatibility baseline on the exact private F365
image. It packages the same `head` and `tail` awk helpers used by the successful
F365 RAM startup. Both radio drivers remain unchanged. It has not been installed
and does not establish persistent automatic startup or client performance.

## Immutable image

- Private directory: `/workspace/user-home/.openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f371-f365-normal-start-compat-device-bound`.
- Image: `openmitrastar-linux510-f371-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH.webformat.bin`.
- SHA-256: `b2eb2d0af57b6beaf47981d575ffd769997135fd46179bed8cb4fc3bd00ae147`.
- Size: **5,382,144 bytes**.
- Manifest SHA-256: `211de602dc6291388552a02418a89c80a174359e4e41380d2a9f3a55e5e23842`.
- Result: `/workspace/user-home/.openmitrastar/devices/hgw500bna-qcv2-a2-primary/analysis/f371-fullimage-20261021T193330Z/result.json`.
- Product version: `lyoko-foundation-6.12.2-f371-normal-start-compat-device`.

The image includes private device identity and must stay local. The full-slot
entry in the manifest is a read-only checksum model, including the preserved
store; it is not a generated flash file.

## Exact scope

The parent is F365 image SHA-256
`43f4655f09eb01d749ca24c003689470b2f7c2d2738333297348e965e56d5355`,
5,382,144 bytes. Parent manifest SHA-256 is
`a73a41e32d793a33ec13c46ef62bbf5890039339d38ef107d04c13b91e19d19c`.

Only six regular files change or are added:

1. `usr/sbin/om-radio5-start`: its single PATH line adds
   `/usr/libexec/openmitrastar/f371-compat`.
2. `usr/libexec/openmitrastar/f371-compat/head`: exact RAM helper bytes.
3. `usr/libexec/openmitrastar/f371-compat/tail`: exact RAM helper bytes.
4. `etc/openmitrastar/release`: candidate identity.
5. `usr/share/openmitrastar/radio5g/artifacts.sha256`: updated starter hash and
   both new helper entries.
6. `usr/share/openmitrastar/storage/artifacts.sha256`: required catalog hash.

F365 already includes `S55-radio5-ap` and the enabled
`Q3_RADIO5_AUTOSTART=1` feature. F371 preserves both byte for byte. Its init
service retains the RADIO5G_ENABLE, MAC producer and calibration admission
checks before executing the normal starter. This fixes utility availability;
physical boot outcome is still untested.

QDRV stays exact F365 SHA-256
`cfb1b5c49eba15a0b114bb695d68dce07629d9600387a26d3c65d7ae573a4b01`;
WLAN stays
`f4f6099b43dd675dd44e7021374f1ea2f4380a4d9d9fd81b1d35ea411984897f`.
Every other existing rootfs entry retains content, mode, owner and topology.
Kernel/config/DT, 2.4 GHz, Ethernet, PSK handling, identity, calibration,
regulatory settings, F355 lifetime pin, existing TX BA policy, disabled sensor,
native/shadow radar admission, watchdog and protected partition policy remain
unchanged. No F367 diagnostic/native DFS components are imported.

## Verification and remaining gates

`tools/build_f371_normal_start_image.py` reuses the established F164 compositor
and exact F365 kernel assets. `tools/f371_rootfs_worker.py` verifies the complete
source catalog, applies the narrow delta, checks shell syntax, exercises five
head/tail fixture cases, repacks SquashFS, then independently extracts and
verifies every entry and catalog. Both independent full image repacks are byte
identical; Bootbase and physical prefix fit pass. No kernel or driver compilation
was performed. The preserved store is read only and exact F365 is bound as the
known artifact rollback, full-slot CRC32 `118901d4`.

**OFFLINE GO; physical NO_GO pending exact artifact authority and fresh device,
protection, readback and rollback gates.** Persistent cold boot, control-plane,
client AUTH/ASSOC/AUTHORIZED, bidirectional traffic, soak, manual `mtd3` recovery
and release acceptance remain UNRUN for this image. Existing RAM startup results
are evidence for the utility fix, not acceptance of F371.

The next separately reviewable candidate can package the qualified F370
observation QDRV atop F371. Keeping that as F372 isolates measurement changes
from this startup compatibility repair. Neither candidate adds hot unload;
F355 still requires a fresh boot after an admitted radio mutation.

Only physical `mtd4/linux_live` is a normal firmware target. `mtd0`, `mtd1`,
`mtd2`, `mtd3`, `mtd5` and logical `mtd6/rootfs_live` remain outside normal writes.
No SSH, UART, runtime mutation, reboot, TFTP, boot-environment change or firmware
write was performed by this work. The legacy fixed-path objective audit was not
run or replaced.
