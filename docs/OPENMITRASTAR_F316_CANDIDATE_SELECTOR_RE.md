# OpenMitraStar F316 Candidate Selector Reconstruction

Date: 2026-09-05

## Result

The pulse-town construction and candidate selection immediately before the
SSR/ITLV dispatcher in OEM `detect_radar` (`0x95cc`) are reconstructed as
portable C.

- Scope: `make_pulse_town`, center-neighbor accounting, direct-candidate
  support and the width-center ITLV fallback.
- Result: `PASS_OFFLINE_CANDIDATE_SELECTOR`.
- Hardware, COM, UART, radio, firmware and MTD: not used.
- OEM `radar.ko`: read-only evidence only; it is not copied by this component.

Implementation:

- `work/kernel-port/modules/f316_radar_classifier/candidate_selector/`
- `f316_candidate_selector.c`
- `f316_candidate_selector.h`
- `test_f316_candidate_selector.c`
- `PROVENANCE.tsv`

## Reconstructed Flow

```text
raw_pulse_t[]
  -> make pulse_info_t town (max 100)
  -> minimum population gate (6 / 4 / 2)
  -> compare every pair among the first 11 pulses
  -> count width and PRI neighbors, including self
  -> choose primary center by maximum PRI neighbors
       tie: lower PRI wins
  -> count supporting pulses before and after the center
       cumulative PRI
       nearest integer multiple of center PRI
       scaled PRI tolerance and width tolerance
  -> enough support: direct SSR candidate
  -> otherwise choose maximum width-neighbor center
       11 neighbors required: ITLV candidate
  -> otherwise no candidate
```

`make_pulse_town` uses the current raw pulse's start/stop for width and the
next raw pulse's start for PRI. Both differences use the exact 27-bit timer
modulus. Width bounds are inclusive.

## OEM Address Map

| Range | Reconstructed behavior |
|---|---|
| `0x96ce..0x974e` | Build the filtered pulse town, capped at 100 entries. |
| `0x978c..0x97c2` | Require 6 normal, 4 OCAC or 2 EU-weather OCAC pulses. |
| `0x97c6..0x9900` | Initialize self-counts and count all width/PRI-neighbor pairs over the first 11 entries. |
| `0x9904..0x998a` | Pick the largest PRI-neighbor cluster; ties select the lower PRI. |
| `0x9af4..0x9b02` | Apply primary-neighbor threshold 3, or 2 for EU-weather OCAC. |
| `0x9cb4..0x9d86` | Walk backward from the center using cumulative PRI and nearest-multiple residual. |
| `0x9f00..0x9fca` | Apply the same support test forward from the center. |
| `0xa010..0xa0e4` | Require support 6/4/2 for small towns or at least 60 percent for towns of 12 or more. |
| `0xa0ee..0xa166` | Select the first maximum width-neighbor center and require all 11 neighbors for ITLV. |
| `0xa174..0xa202` | Downstream evidence identifies the selected routes as ITLV or direct SSR. |

The function-name strings `make_pulse_town` and `find_center_pulse`, relocation
targets, `detect.h` layouts and all constants are cross-referenced in
`PROVENANCE.tsv`.

## Evidence Classification

### Exact

- Raw and town layouts: 16 and 12 bytes.
- Pulse timer mask: `0x07ffffff`.
- Town capacity: 100; center-analysis limit: 11.
- EU software width range: 4..360.
- EU neighbor radii: PRI 5, width 26.
- Inclusive pair comparisons and self-count initialization.
- Primary-center tie-break by lower PRI.
- Small-town support minima 6/4/2 and large-town ratio 3/5.
- ITLV fallback threshold greater than 10, represented as 11.

### Inferred

- `SSR` and `ITLV` names for the two selector outputs come from their immediate
  downstream branches, not retained source-level local variable names.
- The portable API accepts a conventional raw buffer length. The OEM optimized
  hardware loop exposes adjacent-pair behavior but not the original caller's
  source-level count convention.

### Conservative

- A zero center PRI fails the direct-support calculation instead of reproducing
  the OEM division-by-zero assumption.
- Local frequency-hopping selection is intentionally absent. The EU profile
  recovered at `radar_start` sets `localFHdetect=0`; enabling that future mode
  requires its own reconstruction.
- This component selects candidates only. It does not classify SSR/ITLV, invoke
  callbacks, configure RF or make DFS authoritative.

## Verification

The test suite covers profile constants, timer wrap, width filtering, the
100-entry cap, all three population modes, pair counts, tie-breaking, missed
pulse support, the 60-percent gate, ITLV fallback, the exact 11-neighbor
threshold, the first-11 limit, zero-PRI fail-closed behavior and the integrated
build/select API.

Required checks:

```sh
make test
make analyze
make arc-check ARC_CC=arc-linux-gnu-gcc
```

Executed result:

```text
Host GCC strict C11 tests: PASS (12/12)
GCC -fanalyzer: PASS
ARC700/uClibc GCC 15.2.0 object build: PASS
ASan/UBSan: NOT RUN (runtime libraries absent from the available WSL image)
```

No hardware action is part of this result.
