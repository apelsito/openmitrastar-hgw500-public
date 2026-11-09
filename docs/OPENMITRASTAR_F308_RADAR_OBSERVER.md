# OpenMitraStar F308 Radar Acquisition Observer

Date: 2026-09-04

## Result

F308 is a bounded, read-only ARC700/Linux 5.10 radar acquisition observer. It
is an offline module artifact, not a detector and not a firmware candidate.

- Exact F301/F306 kernel lineage: required and verified by the builder.
- Radar ABI provider: complete for link testing.
- RF register writes: none.
- IRQ, timer or worker registration: none.
- Radar callback storage or invocation: none.
- DFS readiness and TX authorization: always false/denied.
- Module load and hardware observation: NOT RUN.
- Router, AELITA, COM3, UART, TFTP, flash and MTD: NOT USED.

## Files

- `work/kernel-port/modules/f308_radar_observer/qtn_radar_observer_f308.c`
- `work/kernel-port/modules/f308_radar_observer/Makefile`
- `tools/build_f308_radar_observer_offline.py`
- `tools/test_f308_radar_observer_offline.py`
- `outputs/kernel-port/f308-radar-observer-v2-20260904/`

## Runtime Design

F308 retains the F302 fail-closed ABI. `radar_start()` returns false,
`radar_get_status()` returns false, registration calls return
`-EOPNOTSUPP`, and no callback pointer is stored. It cannot call qdrv's radar
path or authorize a DFS channel.

The exact F301/F306 kernel has `CONFIG_PROC_FS=y` and no enabled debugfs. F308
therefore exposes modern, read-only procfs files:

```text
/proc/openmitrastar_radar_f308/status
/proc/openmitrastar_radar_f308/snapshot
```

There is no `proc_write` operation.

The observer is inert unless `observe_enable=1` is supplied at module load.
Even then it performs reads only. It maps the Topaz TD1 register window and the
two 256-entry pulse banks, reads six pointer/count registers twice, and reads a
manual ring window of at most 18 pulse pairs twice.

The output exposes only bounded decoded fields:

- masked ring indices and ZC offset;
- pulse start, stop and modulo-2^27 width;
- window-local PRI delta;
- tag and five-bit metadata fields;
- register and pair stability flags;
- bounded counters.

It never emits physical addresses, kernel pointers, full memory dumps,
credentials, MAC addresses or calibration material.

## Why Samples Remain Non-Meaningful

F303 proves the OEM executes a substantial baseband configuration sequence
before acquisition: thresholds, pulse widths, gain, IIR coefficients, capture
mode, pointer resets and memory clearing. F308 deliberately executes none of
those writes.

Consequently every snapshot reports:

```text
configuration_known=0
samples_meaningful=0
chronology_proven=0
physical_rf_detection_proven=0
classification_algorithm=NOT_IMPLEMENTED
```

The manual ring index avoids inventing the optimized OEM pointer conversion.
Stable data may still be stale, unconfigured or owned by another component.

## Build And Link Contract

The builder pins the exact F301/F306 kernel lineage:

- release `5.10.260-openmitrastar-radiohw`;
- exact `.config`, `vmlinux` and `Module.symvers` hashes;
- identical F301 and F306 kernel LZMA hashes.

It performs two reproducible builds, audits all imports/exports and temporarily
rebuilds qdrv without `qdrv_radar_compat.o` to prove that the 16-symbol binary
consumer contract resolves against F308. That qdrv is a link probe only and is
not packaged or loaded.

## Offline Verification

- Two reproducible module builds: byte-identical.
- Provider exports: 18/18 radar ABI symbols.
- Provider imports: 18/18 resolved by the exact F301/F306 kernel.
- Temporary externalized-qdrv link probe: PASS.
- F302/F303/F307/F308 regression: 51/51 PASS.
- Module size: 15,580 bytes.
- Module SHA-256:
  `2a60c95d51cfd00dab25f91eea3d43945e9305c603399036b56710646cd74eca`.
- Packaged `SHA256SUMS`: PASS.

## Next Evidence Step

After F306 completes its physical gates, a later versioned diagnostic image may
package F308 in the SquashFS written to `mtd4`. It must remain disabled and
without autoload. The first physical gate will load that packaged module with
its default `observe_enable=0` to verify the procfs and fail-closed contract.
Only after that may a second bounded gate use `observe_enable=1` while the radio
remains on a proven non-DFS channel. No ad-hoc RAM image or module transfer is
part of this workflow.

Useful pulse acquisition is not expected until a justified subset of the OEM
configuration writes can be introduced one variable at a time. No such write
belongs to F308. F307 replay and a sanitized OEM oracle remain the comparison
framework for every future acquisition or classifier increment.
