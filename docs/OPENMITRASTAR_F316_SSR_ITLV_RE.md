# OpenMitraStar F316 SSR/ITLV reconstruction

Date: 2026-09-05

## Result

F316 reconstructs only the SSR and ITLV classifier portion of the preserved
Quantenna radar module as portable C11. It does not access hardware and is not
a firmware candidate.

- SSR direct width/PRI gate: reconstructed with high confidence.
- ITLV cluster construction and validation: reconstructed with high confidence.
- `detect_radar` SSR/ITLV dispatch: reconstructed for the visible final branch.
- Source or instruction equivalence: NOT PROVEN.
- Hardware, COM, UART, TFTP, radio and MTD: NOT USED.

Implementation:

`work/kernel-port/modules/f316_radar_classifier/ssr_itlv/`

## Evidence base

- OEM `radar.ko` SHA-256:
  `3550945b4affe54ddc5dcc6a3d13bb4caed6f38e1a6d0fb7b295028381e58332`.
- F303 `objdump -dr`, relocation, string and symbol evidence.
- GPL `detect.h` structures and constants.
- `detect_radar` at `0x95cc`.
- `isit_itlv` at `0x90a4`.

No OEM binary bytes are copied into F316.

## Reconstructed behavior

### SSR

The direct SSR gate at `0xa202..0xa23c` accepts one already-selected pulse
candidate only when its width and PRI are inside all four configured bounds.
Every comparison is inclusive.

For the EU-family profile initialized by `radar_start`:

| Parameter | Value |
| --- | ---: |
| SSR PRI | `0x0960..0xc3b4` |
| SSR width | `4..360` |

This corrects the F315 shadow profile: `300` is the EU ITLV PRI-difference
lower bound, while the SSR width upper bound written at `0x66d4` is `360`.

### ITLV

`isit_itlv` performs the following operations:

1. Limit the pulse town to its first 18 entries.
2. Build greedy clusters from unassigned pulses.
3. Compare width and PRI against running cluster sums with growing radii.
4. Reject clusters containing fewer than four pulses.
5. Calculate integer-floor average width and PRI.
6. Apply inclusive ITLV width and PRI bounds.
7. Retain the first four valid cluster centers.
8. Link cluster pairs when width centers are near and PRI-center difference is
   inside the configured interval.
9. Accept exactly two or three linked clusters.
10. Return their PRI centers compactly to the caller.

EU-family values used by this scoped implementation:

| Parameter | Value |
| --- | ---: |
| ITLV PRI | `0x1af4..0x9858` |
| ITLV PRI difference | `300..0x3a98` |
| ITLV width | `7..70` |
| PRI cluster radius | `10` |
| Width cluster radius | `28` |
| Width-neighbor radius | `26` |

The acceptance of two or three linked clusters, but not four, follows the
unsigned range idiom at `0x9552..0x9558`. It is preserved exactly despite being
non-obvious and remains explicitly marked for future instruction-level oracle
confirmation.

### Dispatcher

The final visible dispatcher branch at `0xa174..0xa1f4` does not fall back to
SSR when an ITLV candidate is selected. It calls `isit_itlv` when ITLV is
enabled; a disabled or failed ITLV branch remains rejected. The alternate path
applies the direct SSR gate.

## Provenance

`PROVENANCE.tsv` records each implemented constant and branch with:

- OEM address range;
- source evidence;
- reconstructed behavior;
- confidence;
- remaining gap.

## Tests

The portable suite covers:

- exact EU profile values;
- inclusive SSR boundaries and one-step rejects;
- four-pulse ITLV cluster minimum;
- two- and three-cluster acceptance;
- four-linked-cluster rejection;
- inclusive width-neighbor and PRI-difference boundaries;
- 18-pulse input cap;
- compact PRI output;
- absence of ITLV-to-SSR fallback.

Observed offline verification on 2026-09-05:

- strict host C11 compile and test execution: PASS;
- GCC `-fanalyzer`: PASS;
- ARC700/uClibc cross-compile with warnings as errors: PASS;
- ASan/UBSan: NOT RUN because the analysis distro lacks its runtime libraries.

Compile contract:

```sh
cc -std=c11 -O2 -Wall -Wextra -Werror -pedantic \
  f316_ssr_itlv.c test_f316_ssr_itlv.c -o test_f316_ssr_itlv
./test_f316_ssr_itlv
```

## Remaining gaps

- The upstream `detect_radar` pulse-town candidate selector is intentionally
  outside this SSR/ITLV-only scope.
- Other regional profiles are not reconstructed here.
- The portable core consumes normalized `pulse_info_t`-equivalent entries; it
  does not implement FIFO acquisition or `radar_preprocess`.
- No deterministic ARC700 execution oracle exists yet, so instruction-level
  equivalence cannot be claimed.
- No physical radar detection, callback, CAC or DFS operation is claimed.

Status: `PASS_OFFLINE_BRANCH_RECONSTRUCTION_EQUIVALENCE_UNPROVEN`.
