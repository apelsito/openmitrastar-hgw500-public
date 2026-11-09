# OpenMitraStar F316 Radar Post-Detection Gate Reconstruction

Date: 2026-09-05

## Result

This work reconstructs only the bounded post-detection and callback contract
inside the preserved OEM `radar_poll_work`, including the metadata helper at
`.text+0x8ef8` and the sole indirect callback at `.text+0x4bbe`.

- Portable C implementation: PASS.
- Last-detection metadata helper: HIGH-CONFIDENCE RECONSTRUCTION.
- Ten-sample rate suppression: HIGH-CONFIDENCE RECONSTRUCTION.
- Final callback truth table: EXACT AT CONTROL-FLOW LEVEL.
- Pulse-history ring layout and sums: HIGH-CONFIDENCE RECONSTRUCTION.
- Preceding bad-state/history matcher: EXPLICIT INPUT, EQUIVALENCE UNPROVEN.
- Hardware, COM, UART, SSH, TFTP, radio and MTD: NOT USED.

Implementation:

`work/kernel-port/modules/f316_radar_classifier/postfilter/`

## Provenance

Primary private analysis input:

- OEM `radar.ko`, SHA-256
  `3550945b4affe54ddc5dcc6a3d13bb4caed6f38e1a6d0fb7b295028381e58332`.
- F303 disassembly, relocations and function map under
  `outputs/kernel-port/f303-oem-radar-re-20260904/`.
- `work/sources/Quantenna-GPL/drivers/radar/detect.h`.
- `work/sources/Quantenna-GPL/drivers/radar/radar.h`.

No OEM executable bytes are copied into the F316 source. Address-by-address
provenance is recorded in `postfilter/PROVENANCE.tsv`.

## Recovered Data Layout

The GPL headers and direct `.bss` references align exactly:

| OEM location | Field |
|---|---|
| `.bss+0x1070` | registered qdrv callback |
| `detect_cfg+214` / `.bss+0x137a` | `lsrDetectEnable` |
| `detect_cfg+215` / `.bss+0x137b` | `detected_lsr_flag` |
| `detect_cfg+219` / `.bss+0x137f` | `rateFilter` |
| `detect_cfg+220` / `.bss+0x1380` | `maxRate` |
| `detect_cfg+224` / `.bss+0x1384` | `maxInstRate` |
| `detect_sta+632` / `.bss+0x1648` | `radar_ps_buf[10]` |
| `detect_sta+672` / `.bss+0x1670` | `last_radar_ps_cnt` |
| `detect_sta+680` / `.bss+0x1678` | `last.numPulse` |
| `.bss+0x167c..0x1684` | `last.pri[3]` |
| `.bss+0x1688` | `last.pw` |
| `detect_sta+12` / `.bss+0x13dc` | `detected_rjt` |

`radar_cb_t` uses one 240-entry pulse-history buffer with independent 20-entry
and 240-entry indices and sums. F316 preserves that shared storage and captures
both overwritten values before writing, so overlapping indices remain
deterministic.

## Metadata Helper At 0x8ef8

The helper receives a `pulse_info_t` candidate, pulse count, a three-PRI vector
and an interleaving flag. It always stores the pulse count. When a candidate is
present it stores the width and either:

- direct detection: `candidate->pri`, then two zero PRIs;
- interleaved detection: all three values from the supplied PRI vector.

A null candidate produces zero width and PRIs. The helper only records the
candidate; it does not make the later callback decision.

## Rate Suppression

At `0x4b36..0x4b82`, when `rateFilter` is enabled, the OEM worker:

1. sums exactly ten `radar_ps_buf` samples;
2. requests suppression when the sum is strictly greater than `maxRate`;
3. otherwise requests suppression when `last_radar_ps_cnt` is strictly greater
   than `maxInstRate`.

The EU-family initialization stores `maxRate=65` and `maxInstRate=120`. F316
uses a fixed ten-entry ring and checked unsigned arithmetic. The producer,
cadence and physical unit of each rate sample remain outside this scope.

## Final Callback Condition

The exact optimized condition at `0x4b2e..0x4bc6` is represented as:

```text
candidate = candidate_detected
lsr_gate = lsr_history_reject && detected_lsr_flag && lsr_enabled
suppression = history_reject || rate_reject || lsr_gate

if candidate && suppression && !noreject:
    detected_rjt++
else if candidate && callback_registered:
    callback()
```

`noreject` is not inferred from a name alone: `/proc/radar` writes
`.bss+0x101d` at `0x56d8..0x571a`, and the byte bypasses the suppression branch
immediately before `0x4bbe`. It does not bypass the callback null check.

The portable function returns `callback_should_fire=true`; it deliberately does
not hold or execute a function pointer.

## Explicit Gaps

- The full upstream derivation of optimized register `r5` is not yet proved;
  F316 names it `history_reject` and requires the caller to supply it.
- The full upstream derivation of `r19` is not yet proved; F316 names it
  `lsr_history_reject` and reproduces only its exact three-way final use.
- The exact meanings of the two pulse counts inserted into the 20-entry and
  240-entry history views remain unresolved.
- The bad-state timer transitions using constants 9, 24 and step 2 are visible
  in the preceding block but are not claimed as source-equivalent here.
- The rate sample producer, interval and unit are not reconstructed.
- Callback locking, unregister synchronization and qdrv ownership are kernel
  integration work, not part of this portable module.

These gaps are visible in the API rather than hidden behind invented field
names. Therefore this component is suitable for deterministic composition and
differential testing, but not yet for authorizing the F316 DFS callback.

## Test Contract

The deterministic suite covers:

- all exact history/state constants;
- EU-family rate defaults;
- direct, interleaved and null-candidate metadata recording;
- 20-entry and 240-entry history wrap and running sums;
- ten-entry rate-ring replacement;
- strict `>` boundaries for window and instantaneous rate;
- disabled rate filtering;
- exact history and three-way LSR suppression inputs;
- `noreject` bypass;
- missing callback and missing candidate behavior;
- combined suppression bits and invalid arguments;
- all 128 combinations of candidate, history, rate, LSR and override booleans.

Run with:

```bash
make -C work/kernel-port/modules/f316_radar_classifier/postfilter test
make -C work/kernel-port/modules/f316_radar_classifier/postfilter analyze
```

The expected result is 20 deterministic behavioral groups passing under strict
C11 compilation and a clean GCC `-fanalyzer` pass.

Verification executed on 2026-09-05:

- native C11 build with `-Wall -Wextra -Werror -pedantic`: PASS;
- 20/20 deterministic behavioral groups: PASS;
- exhaustive 128-row callback truth table: PASS;
- GCC `-fanalyzer`: PASS;
- ARC700/uClibc object build: PASS;
- ARC700/uClibc executable link: PASS;
- ASan/UBSan: NOT RUN because the active WSL image lacks `libasan.so.8.0.0`
  and `libubsan.so.1.0.0`.

The sanitizer limitation is a host-tooling gap. It is not counted as a passing
sanitizer result and does not affect the strict native or ARC700 build results.
