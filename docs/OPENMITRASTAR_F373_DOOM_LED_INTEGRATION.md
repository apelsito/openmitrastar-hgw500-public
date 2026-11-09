# F373 Doom in English, LED CLI and boot timing — 2026-10-22

The complete requested offline integration was built twice from exact F372.
Both independently packed and extracted SquashFS files are byte-identical.
**F373 is NO_GO_SLOT_FIT.** No oversized webformat or firmware flash artifact
was generated, and no device access, flash, reboot or runtime change occurred.

Authoritative private analysis:
`/workspace/user-home/.openmitrastar/devices/hgw500bna-qcv2-a2-primary/analysis/f373-doom-led-20261021T223307841061Z/result.json`.
UTC filenames use 2026-10-21; the local Europe/Madrid date is 2026-10-22.
The analysis SquashFS contains the device's existing identity and stays private.

## Actual complete combined measurement

| Item | Bytes |
|---|---:|
| F372 original rootfs | 3,809,280 |
| F373 combined rootfs, each lane | 7,782,400 |
| Available rootfs window, `0x460000` | 4,587,520 |
| Actual rootfs overflow | **3,194,880** |
| Existing rootfs offset, `0x180000` | 1,572,864 |
| Projected unpadded image size | 9,355,264 |
| Physical firmware prefix limit, `0x5e0000` | 6,160,384 |
| Projected prefix overflow | **3,194,880** |

Both analysis rootfs SHA-256:
`04e39e7fa9d6e76154dd9ce8796c7d0b2e6169efba2016f81411230229dc7379`.
The full image size is arithmetic from the measured packed rootfs plus the
existing fixed offset; there is no corresponding flash file.

This supersedes a separate-game compression estimate with actual co-packing.
No files, license notices, source archive, game content or existing driver
components were removed to make a smaller substitute appear to satisfy scope.
Protected partitions, the preserved store and logical MTD aliases provide no
additional permitted firmware capacity.

## Exact integrated changes

The source is the unchanged F372 image SHA-256
`e8f7315c286e98d73f6bf4152c652f4633c8f63bd4a72b8a300e6859af619ef9`,
manifest SHA-256
`e4d9502d90fcb64c289c8369c41231a9dd837e05d2133e13953d3482b6abe0b5`.
Product identity becomes
`lyoko-foundation-6.13.0-f373-doom-english-led-timing-device`.

- All ten `www/Doom` files from
  `outputs/doom/browser-20261022-r2-touch/www/Doom` are packaged. Only index.html
  comes from `english-episode1-20261021T222750344251Z`; its SHA-256 is
  `f05c849f945e56f4250a7800e627a732e9711746465c8359d5cfeb270d5baa33`.
  The page is English and retains the original episode-one shareware selection.
- `usr/sbin/om-ledctl` is the exact qualified LED revision2,
  SHA-256 `0b2509b8dbd628174b952d6b115c6e6be3a39f89b96514e2f17290fae5e81753`.
- `etc/init.d/rcS` is the exact timing-only candidate,
  SHA-256 `d5870a307ee1514689ca134cb51a25effdc932ccaa715168737cdedf65e30653`.
- Release/build identity, a new ten-entry Doom artifact catalogue, and the
  existing storage catalogue are updated to bind the exact packaged bytes.

The full delta is **15 regular files and two new directories**; **463 original
entries remain unchanged**, including their modes, owners, symlinks and hardlink
metadata. Both pack/extract lanes include complete before/after inventories.
Six catalogues are checked after extraction: Doom10, radio2g12, radio5g40,
storage12, temperature5 and watchdog2 entries. The inherited one-space radio2g
catalogue format is preserved exactly. The first attempt stopped on its format;
that failure is retained under its separate timestamp, not overwritten.

Kernel, radio drivers, calibration, regulatory inputs, device identity,
Ethernet and all other original files remain unchanged. LED and rcS shell syntax
pass. No physical LED restore/electrical proof, boot-speed improvement, Wi-Fi
client/traffic acceptance, persistent cold boot or final release is inferred.

## Reproducibility and recovery

`tools/build_f373_doom_led_image.py` runs the new
`tools/f373_rootfs_worker.py` in the existing REA-Linux build environment with
the original deterministic XZ/128KiB SquashFS settings, epoch1790006400 and one
processor. Both build lanes are independently extracted and compared. Inputs
are hashed before/after. The exact existing binaries are pinned and rechecked:

- `/usr/bin/mksquashfs`:
  `47d5c1af3da11864e64c9dc6bb4e568719dcc315e6a744e79381ce3374fb7393`.
- `/usr/bin/unsquashfs`:
  `b305985eb764b6d0ef757571e3e44044ebf71c827c4263efe576e9e14b4abcfb`.

The builder uses the existing compositor only if the measured rootfs and prefix
fit checks both pass. They fail here, so no firmware file is constructed and no
new private firmware release directory is promoted.

F365 return references and the preserved store remain exact and unchanged.
Fresh verified manual mtd3 recovery, source-bound physical backend/lease,
current readback and exact artifact authority remain independent requirements.
The historical mtd3 rootfs/management recovery record is NO_GO; a Bootbase
kernel contract alone cannot supply recovery PASS. F373's measured overflow is
already sufficient to reject installation under the current permitted layout.
