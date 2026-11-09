# OpenMitraStar F316 OEM Radar Preprocess Reverse Engineering

Date: 2026-09-05

## Result

This work reconstructs only the OEM `radar_preprocess` routine at
`.text+0x26e8..0x2c13` from the immutable Quantenna `radar.ko` with SHA-256:

```text
3550945b4affe54ddc5dcc6a3d13bb4caed6f38e1a6d0fb7b295028381e58332
```

The portable implementation is under:

```text
work/kernel-port/modules/f316_radar_classifier/preprocess/
```

It is not integrated into a kernel module or firmware. No router, UART, COM,
TFTP, radio, MTD or runtime state was accessed.

## Recovered Signature And Data Flow

The four ARC argument registers and both worker call sites at `0x41d8` and
`0x42d0` support this reconstructed contract:

```c
raw_pulse_t *radar_preprocess(
    unsigned *total_count,
    raw_pulse_t *new_pulses,
    unsigned new_count,
    int *count_delta);
```

The OEM implementation is stateful. It copies the previous processed pulse
array into a scratch array, processes a new batch, updates the persistent array
pointer/count, and returns `NULL` when no pulse remains. The F316 API makes that
state explicit through `struct f316_preprocess_state`.

`raw_pulse_t` is exactly 16 bytes:

```text
+0x00 start
+0x04 stop
+0x08 max_power
+0x0c tagged (byte, followed by padding)
```

The normalized `pulse_info_t` used immediately downstream is exactly 12 bytes:

```text
+0x00 start
+0x04 width = (stop - start) & 0x07ffffff
+0x08 PRI   = (next.start - current.start) & 0x07ffffff
```

The PRI belongs to the current pulse and points forward to the next pulse. The
last raw pulse cannot produce a PRI and is not emitted by this conversion.

## Exact Preprocess Algorithm

For each pulse selected from the new batch:

1. Add the current timestamp epoch/base to `start` and `stop`.
2. Compare the modular gap from the previous `stop` to the current `start`.
3. Merge when the gap is **less than or equal to** `mergeSeparationMax`.
4. A merge always extends `stop`, retains the maximum `max_power`, and ORs the
   tag only when tag mode is enabled.
5. If the gap is too large and the previous pulse is tagged in tag mode,
   replace that previous pulse with the current pulse and count one tagged
   discard.
6. Otherwise finalize the previous pulse. Reject width below the lower bound or
   above the upper bound; if width passes, reject power below `maxPowTh`.
7. Append the current pulse.
8. Finalize the last pulse using the same width-then-power order. A final tagged
   pulse is discarded before those filters.

All timestamp, width, separation and PRI subtraction is modulo 27 bits. Width
and power bounds are inclusive.

The routine also updates the exact statistics represented by
`numReadPulse`, `numLeftPulse`, `numTagPulse`, `numMergePulse`,
`numPwFilterPulse` and `numPowFilterPulse`. F316 exposes equivalent per-batch
counters without reproducing the unrelated hardware watchdog/reset tail.

## Constant Provenance

| Constant | Value | Classification | Evidence |
|---|---:|---|---|
| Pulse modulus | `0x08000000` | exact | `detect.h` and OEM 27-bit masks |
| Pulse mask | `0x07ffffff` | exact | `detect.h`; `bmsk ...,0x1a` |
| Source-index ring | `128` | exact | `MAX_RADAR_PULSE_READ_CNT`; masked stores at `0x2852`, `0x2894`, `0x292a` |
| EU merge separation | `500` | exact | `detect_cfg_t.mergeSeparationMax`, `.bss+0x133c` |
| EU hardware width lower | `4` | exact | `hwPwLBnd`, `.bss+0x12b4` |
| EU hardware width upper | `360` | exact | `hwPwUBnd`, `.bss+0x12b0` |
| EU software width lower | `4` | exact | `swPwLBnd`, `.bss+0x12bc` |
| EU software width upper | `360` | exact | `swPwUBnd`, `.bss+0x12b8` |
| EU minimum power | `1` | exact | `maxPowTh`, `.bss+0x12a8` |
| EU maximum read count | `128` | exact | `maxPulseReadCnt`, `.bss+0x12fc` |
| Raw timer tick duration | unknown | inferred | Header comment equates `MIN_PULSE_SEP=5` with 5 us, while the active EU profile stores 500; no conversion is asserted |
| Early capacity rejection | caller capacity | conservative | F316 refuses a worst-case overflow before mutation; OEM relies on fixed global storage |

The operational constants are available at runtime through
`f316_constant_catalog()`, with their evidence classification and source.

## Differences From F315

- Removes the synthetic `stable` filter, which does not exist in OEM
  `raw_pulse_t` or `radar_preprocess`.
- Uses the exact OEM `max_power` field instead of an inferred five-bit
  `power_code`.
- Preserves processed pulses between calls.
- Reproduces tagged-pulse replacement and terminal tagged-pulse removal.
- Applies width and power filters when a pulse is finalized, in OEM order.
- Uses the exact inclusive merge boundary.
- Derives PRI from the next pulse, matching `detect_radar`, rather than from the
  previous pulse.
- Reproduces the tag-dependent maximum-read branch and source-index ring.

## Deliberately Excluded

- Classifier logic (`SSR`, `ITLV`, `FH`, `LSR`, chirp and weather radar).
- QT4 FIFO and zero-crossing acquisition.
- MMIO writes, baseband locking and the polling reset watchdog.
- `detect_radar`, callback dispatch, CAC, NOP and channel evacuation.
- Kernel/F315 integration and any firmware image.

Those exclusions keep this result bounded to the requested preprocessing
routine and prevent unproven classifier behavior from being presented as OEM
equivalence.

## Tests

`test_f316_preprocess.c` covers:

- exact structure sizes and constant provenance;
- normal and wrapped 27-bit subtraction;
- inclusive merge threshold and non-merge immediately above it;
- stop extension, maximum-power retention and tag OR;
- tagged replacement and final tagged discard;
- width-before-power filtering and inclusive limits;
- timestamp-base application and state across batches;
- tag-dependent `maxPulseReadCnt` behavior;
- fail-closed capacity handling;
- forward PRI direction, wrap and software-width filtering.

Run with:

```bash
make -C work/kernel-port/modules/f316_radar_classifier/preprocess test
```

The test build is strict C11 with `-Wall -Wextra -Werror -pedantic`.

Executed result:

```text
Host GCC 15.2.1 strict build: PASS
12/12 behavioral cases: PASS
ARC700 uClibc GCC 15.2.0 object build: PASS
ASan/UBSan: NOT RUN (runtime libraries absent from the available WSL image)
```
