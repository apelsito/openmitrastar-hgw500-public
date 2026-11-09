# OpenMitraStar F301 DFS and regulatory audit

Date: 2026-09-04

## Scope

This is a local, read-only audit of the exact F301 artifact and existing
physical evidence. No router, radio, UART, TFTP, reboot, flash or MTD operation
was performed. The Spain policy is an engineering interpretation of the local
project sources, not legal advice.

## Current result

F301 has a valid non-DFS Spain baseline, but it does not have an operational
DFS detector.

- Exact installed candidate: `4c280e84...b87262`.
- Physical readback: region `ES`, code `21317`, channel 36, 80 MHz, DOTH 1.
- The driver-level `get_reg_is_eu` readback is still `0`; the ES region string
  is therefore not proof that the DFS requirement backend resolved to EU.
- The exact SquashFS contains the pinned regulatory database and ES power
  table.
- Boot enables DOTH, TPC and a 30-second TPC interval.
- DFS/CAC/CSA/channel-availability readbacks are exposed read-only.
- `qtn-dfs-control-v1` is disabled.
- No `qtn_radar_native.ko` is packaged.
- The exact qdrv lineage links `qdrv_radar_compat.o`.
- `radar_start()` warns that the proprietary detector is unavailable and
  returns false; DFS requirement reporting remains unknown.

Therefore F301 correctly blocks DFS transmission. The available qdrv and WLAN
code contains CAC, CSA, NOP and radar-event plumbing, but that plumbing is not
a detector and cannot prove regulatory operation by itself.

## Channel-width correction

The previous UI policy classified weather-radar CAC from the primary channel
alone. A safe gate must classify the complete occupied block.

- Primary 116 at 80 MHz occupies 116/120/124/128 and therefore intersects the
  5600-5650 MHz weather-radar interval. Its minimum gate CAC is 600 seconds,
  not 60/70 seconds.
- The same applies to primary 116 at 40 MHz when the secondary is 120.
- Primaries 132/136/140 at 80 MHz require a complete 132/136/140/144 block,
  while channel 144 is absent from the F301 ES contract. They must fail closed.
- Channel 140 at 40 MHz likewise lacks an admitted partner in the current
  contract and must fail closed.
- Every 40 MHz DFS test must verify the actual secondary channel before using
  a CAC classification.

## Next physical gate

### Immediate channels 36-48

This gate is implementable using the existing bounded Quantenna control path.
It should first test one non-DFS move, preferably channel 44 at the existing
80 MHz width, then restore channel 36 exactly.

PASS requires exact F301 identity, region/power preservation, AELITA on the
target channel, 32 MiB in each direction, 120 seconds connected, 2.4 GHz and
management health, zero fatal markers, exact configuration restoration and no
MTD writes.

### DFS channels

Current status: `BLOCKED_DFS_RADAR_BACKEND_UNAVAILABLE`.

A future versioned mtd4 candidate must first provide a native Linux 5.10 radar
backend. The first DFS target should be a non-weather 20 MHz channel such as
100, with a minimum 70-second CAC plus observation margin. The gate must prove
TX suppression during CAC, continuous radar monitoring after CAC, association,
traffic and rollback.

The private `doth_radar` event may test CSA, evacuation and NOP plumbing. It
does not prove physical radar detection. Final radar PASS requires an
authorized calibrated radar source, automatic evacuation and 1800-second NOP
evidence. Without that source the result remains blocked, not partially passed.

## Dry-run

```powershell
python tools\f301_dfs_es_plan.py `
  --channel 100 `
  --bandwidth 20 `
  --output outputs\preflight\f301-dfs-es-plan\plan.json
```

Use `--require-dfs-ready` when an automated caller must receive a nonzero exit
until a native backend exists.
