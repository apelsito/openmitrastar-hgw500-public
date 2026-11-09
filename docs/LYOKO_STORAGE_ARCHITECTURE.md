# Lyoko storage architecture

An MTD device is SPI NOR flash, not RAM. Lyoko should separate package storage
from package execution:

```text
Persistent flash: lyoko_store
        -> signed IPK archives and package state
        -> verified during boot/install
Volatile DDR: /run/lyoko-packages (tmpfs)
        -> extracted binaries and libraries
        -> recreated after every boot
```

## Proposed physical layout

Keep the existing physical `mtd4/linux_live` slot and subdivide its contents:

| Region | Flash offset | Size |
|---|---:|---:|
| uImage header + kernel | `0x7e0000` | `0x180000` |
| `rootfs_live` SquashFS | `0x960000` | `0x460000` |
| `lyoko_store` JFFS2 | `0xdc0000` | `0x1c0000` |
| existing protected `mtd5/data` starts | `0xf80000` | `0x080000` |

With F177, the SquashFS is `0x35f000` bytes. A `0x460000` rootfs window leaves
`0x101000` bytes (about 1 MiB) for future immutable-system growth, while
`lyoko_store` receives `0x1c0000` bytes (1.75 MiB, 28 erase blocks).

## Runtime policy

- Mount a dedicated tmpfs at `/run/lyoko-packages`, initially capped at 8 MiB.
- tmpfs consumes DDR only for pages actually used; it is not preallocated.
- At boot, verify selected IPKs from `lyoko_store` and extract them to tmpfs.
- Never execute directly from JFFS2 when a RAM copy is practical.
- Never use NOR flash as swap.
- Never use `mtd3/linux_safety` or protected `mtd5/data` for packages.

## Required flasher change

Once `lyoko_store` exists, normal firmware updates must erase/write only the
first `0x5e0000` bytes of physical `mtd4`, preserving its final `0x1c0000`
bytes. Full-slot erase becomes forbidden unless the user explicitly requests a
store reset after backup.

This is currently an offline proposal. No partition table, MTD window, mount or
flash procedure has been changed on the physical router.

The prefix-preservation model is exercised with:

```powershell
python tools\simulate_f178_preserving_flash.py `
  --output outputs\kernel-port\f178-storage-split-plan-20260901\flash-simulation.json
```

The simulation uses a deterministic synthetic 16 MiB SPI image. It erases and
writes only the proposed `0x5e0000` live prefix, then proves the candidate,
`lyoko_store`, `mtd3` and `mtd5` hashes independently.
