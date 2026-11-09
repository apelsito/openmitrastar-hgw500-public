# OpenMitraStar F316 LSR, Chirp And Weather Reconstruction

Date: 2026-09-05

## Result

F316 reconstructs only the portable long-sequence radar, chirp and weather
classifier lane requested for the HGW-500BNA-QCv2. It does not access the
router and is not wired to qdrv or the QT4 radar block.

- Portable C implementation: PASS.
- `verify_burst` structural reconstruction: PASS.
- `are_zcs_linear` coefficient and threshold reconstruction: PASS.
- `lsr_detect` / `lsr_detect_poll` state model: PASS_WITH_GAPS.
- Inlined `verify_chirp` / `is_it_tone`: CONSERVATIVE_RECONSTRUCTION.
- EU weather decision: CONSERVATIVE_RECONSTRUCTION.
- Hardware, COM, UART, SSH, TFTP, MTD and RF: NOT USED.
- OEM classifier equivalence: NOT CLAIMED.

Implementation:

`work/kernel-port/modules/f316_radar_classifier/lsr/`

## Provenance

Primary private analysis input:

- OEM `radar.ko`, SHA-256
  `3550945b4affe54ddc5dcc6a3d13bb4caed6f38e1a6d0fb7b295028381e58332`.
- F303 disassembly and function map under
  `outputs/kernel-port/f303-oem-radar-re-20260904/`.
- `work/sources/Quantenna-GPL/drivers/radar/detect.h`.
- `work/sources/Quantenna-GPL/drivers/radar/radar.h`.

No OEM binary bytes are copied into the F316 source. The coefficient arrays
are numeric algorithm data recovered from the named `.data` symbols `Em` and
`av`; their role is independently confirmed by the `are_zcs_linear` body.

## Recovered Contract

### `verify_burst` at `0xa46c`

The OEM function consumes one to three 16-byte pulse records. The recovered
checks are:

- width is `(stop - start) & 0x07ffffff`;
- every width lies inside `lsrPwLBnd..lsrPwUBnd`;
- adjacent widths differ by at most `lsrPwNeighborRadius`;
- adjacent pulse starts produce a PRI inside the LSR range;
- the two-pulse path contains an allowance consistent with one missing pulse.

F316 implements the missing-pulse allowance conservatively as a PRI inside
twice the direct lower and upper bounds. The exact ARC condition-code behavior
of the optimized OEM branch remains a gap.

### `are_zcs_linear` at `0xa670`

This helper is reconstructed directly:

- eleven 11-tap `Em` rows are applied to the current and previous windows;
- absolute row responses are accumulated separately;
- both accumulated energies must be at least `0x249ef`;
- the 11-tap `av` vector produces an absolute frequency estimate;
- the estimate must be in `0x1389..0x124f7`;
- failure returns no valid frequency.

The tests include a fixed 12-sample vector with independently calculated
energies `12940393` and `11723677`, and frequency `39932`.

### LSR state machine

The binary establishes these states and events through strings and control
flow:

```text
reset/unlikely -> likely -> detected
                  |  ^
                  +-- invalid/timeout
```

It also proves counters for bursts, invalid input, lost pulses, chirp detected,
chirp rejected and insufficient information. `lsr_detect_poll` only reports a
hit from the likely state and exports the final statistics before resetting.

F316 preserves this state shape without Linux timers. Time is represented as
explicit poll ticks, making the classifier deterministic and testable.

## OEM-Family Constants

The LSR-enabled profile assigned by `radar_start` provides:

| Field | Value | Evidence |
|---|---:|---|
| pulse width | `450..1050` | stores at config offsets 76/80 |
| PRI | `9900..20100` | stores at offsets 68/72 |
| width neighbor | `28` | offset 112 |
| minimum chirp detections | `7` | offset 184 |
| maximum chirp rejections | `4` | offset 188 |
| detection/rejection delta | `12` | offset 192 |
| chirp frequency radius | `2700` | offset 196 |
| invalid maximum | `26` | offset 84 |
| maximum lost pulses | `13` | offset 260 |
| short timer | `3750` | offset 172 |
| long timer | `10500` | offset 264 |
| burst range | `6..20` | offsets 268/272 |

The EU branch disables the LSR classifier and uses a separate inlined weather
path. Consequently F316 does not pretend that the LSR profile itself is an EU
weather profile.

## Chirp And Tone Reconstruction

`verify_chirp` and `is_it_tone` survive as function names in OEM read-only data
but were inlined by GCC 4.2.1. F316 therefore composes only evidenced
primitives:

1. Evaluate bounded overlapping zero-crossing windows with
   `are_zcs_linear`.
2. Reject a set of frequencies whose span stays inside the recovered
   `chirp_town_freq_th` neighborhood.
3. Require enough valid windows, a minimum frequency span and a dominant
   monotonic direction before calling the row chirp-like.
4. Return `NO_INFORMATION` when correlation cannot establish enough valid
   frequencies.

The minimum-window and monotonic-percentage policy is deliberately visible in
the profile rather than disguised as an OEM constant.

## Weather Reconstruction

The OEM dispatcher contains a separate inlined `check_eu_weather_ocac` path.
The GPL header proves both the minimum weather pulse-town size and detection
threshold as two. F316 therefore requires:

- an externally established weather-channel context;
- at least two valid bursts;
- at least two chirp detections;
- more chirp detections than rejections.

Channel identification, CAC, evacuation and NOP are intentionally outside this
classifier directory.

## Known Gaps

- Exact inlined `verify_chirp` branch equivalence is not proved.
- Exact inlined `is_it_tone` score is not proved.
- The optimized one-lost-pulse branch in `verify_burst` needs an executable OEM
  oracle or physical vectors for exact condition-code confirmation.
- OEM timer units are not yet mapped to Linux 5.10 polling intervals.
- The relationship between ZC row ownership and pulse history needs physical
  acquisition evidence.
- Weather false-positive and false-negative performance is unmeasured.
- No callback may be enabled from this implementation until vector and
  physical radar gates prove the remaining policy.

## Test Contract

The host test suite covers:

- 27-bit wrap arithmetic;
- exact OEM-family profile values;
- valid, invalid and missing-pulse burst paths;
- exact `Em` / `av` correlation output;
- tone discrimination;
- LSR state transition and timeout reset;
- weather-context gating;
- zero-information chirp behavior.

Verification performed on 2026-09-05:

- native C11 build with `-Wall -Wextra -Werror -pedantic`: PASS;
- ten deterministic test groups: PASS;
- GCC `-fanalyzer`: PASS;
- ARC700/uClibc GCC 15.2.0 object and executable link: PASS;
- ASan/UBSan: NOT RUN because the active WSL image lacks its runtime
  libraries; this is a host-tooling limitation, not a passing sanitizer gate.

The code is freestanding in behavior: fixed-size state, no allocation, no
floating point, no kernel headers and no operating-system calls.
