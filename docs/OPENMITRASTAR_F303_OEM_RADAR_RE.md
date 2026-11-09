# OpenMitraStar F303 OEM Radar Entry-Path Reconstruction

Date: 2026-09-04

## Result

The preserved OEM `radar.ko` is sufficiently mapped to define a reproducible
offline acquisition and dispatcher harness. It is not sufficiently recovered
to claim a source-equivalent DFS classifier.

- OEM binary provenance: PASS.
- ARC700 ELF disassembly: PASS.
- Pulse FIFO acquisition map: PASS.
- Zero-crossing acquisition map: PASS.
- SSR/ITLV/LSR/chirp dispatcher map: PARTIAL, control flow established.
- Exact proprietary classification mathematics: NOT RECOVERED.
- `mark_radar` callback gate: PASS at control-flow level.
- Hardware, radio, module load, UART, SSH, TFTP, flash and MTD: NOT USED.

The F303 harness decodes pulse words and models the observed dispatcher using
oracle classifier results. It always reports `classification_algorithm` as
`NOT_IMPLEMENTED`.

## Inputs And Provenance

OEM module:

`work/hgw500-rootfs-live/squashfs-root/lib/modules/2.6.35.12/extra/radar/radar.ko`

- ELF32 little-endian ARCompact, ARC700 legacy ABI.
- Linux vermagic: `2.6.35.12 mod_unload ARC700`.
- SHA-256: `3550945b4affe54ddc5dcc6a3d13bb4caed6f38e1a6d0fb7b295028381e58332`.
- `.text`: `0xce94` bytes.
- Symbols and relocations are retained; local static function symbols are
  mostly stripped.

Source evidence:

- `work/sources/Quantenna-GPL/drivers/radar/radar.h`
- `work/sources/Quantenna-GPL/drivers/radar/detect.h`
- `work/linux510-radio-port/quantenna-v6-scheduler-diag/qdrv/qdrv_radar.c`

Tooling:

- `arc-snps-linux-uclibc-readelf`
- `arc-snps-linux-uclibc-objdump`
- local `strings`

Raw outputs are preserved under
`outputs/kernel-port/f303-oem-radar-re-20260904/`.

## Entry Path

```text
qdrv sys_start_radarmod(region)
  -> radar_start(region)
       programs QT4 radar block with interrupt disabled
       initializes detect_cb / LSR state
  -> radar_set_bw()
  -> radar_disable()
  -> radar_register(mark_radar)

qdrv sys_enable_rdetection()
  -> radar_enable()
       radar_clear_pt()
       detect_reset()
       schedule_delayed_work(radar_poll_work)

radar_poll_work [inferred entry 0x3af8]
  -> lock baseband
  -> read pulse FIFO pointers and pulse banks
  -> read zero-crossing RAM when enabled
  -> unlock baseband
  -> radar_preprocess() [inferred entry 0x26e8]
  -> detect_radar_poll()
  -> detect_radar(raw, count, prior_window_count, zc_cb)
       -> SSR direct bounds path
       -> isit_itlv()
       -> inlined FH / EU-weather checks
       -> lsr_detect()
            -> verify_burst() [inferred]
            -> verify_chirp() [inlined/name evidenced]
            -> are_zcs_linear() [inferred]
            -> is_it_tone() [inlined/name evidenced]
  -> inlined check_radar post-filter
  -> registered callback at .bss+0x1070
       -> qdrv mark_radar()
       -> qdrv_radar_detected(ic, 0)
```

`radar_poll_work` is not an ELF symbol. Its address is high-confidence because
`.rela.data` binds the delayed-work function pointer at `.data+0x0c` to
`.text+0x3af8`, its body references the `radar_poll_work` `__func__` string,
and it both consumes and requeues the same delayed work.

## Pulse FIFO Acquisition

The polling worker holds the Quantenna baseband mutex around the MMIO snapshot.
The relevant Topaz registers and memories are:

| Purpose | Address | Evidence |
|---|---:|---|
| Pulse count / legacy pointer | `0xe6091518` | `QT4_RADAR_CNT_L` and worker/reset accesses |
| Legacy low pointer | `0xe609151c` | `QT4_RADAR_PTR_L` |
| Legacy high pointer | `0xe6091520` | `QT4_RADAR_PTR_H` |
| Interrupt enable | `0xe6091524` | written `0` by `radar_start`; polling is used |
| Current ZC memory pointer | `0xe6091530` | `QT4_RADAR_CUR_CHMEM_ADR` |
| New-mode start pointer | `0xe609156c` | worker read |
| New-mode pulse pointer | `0xe6091570` | worker and exported snapshot read |
| Pulse memory L | `0xe6401000` | `QT4_RADAR_MEM_L` |
| Pulse memory H | `0xe6401400` | `QT4_RADAR_MEM_H` |
| Zero-crossing RAM | `0xe6400000..0xe6400fff` | header and worker reads |

At `0x3eaa..0x3f1e`, the worker reads paired 32-bit values from the two pulse
banks and constructs a 16-byte `raw_pulse_t`:

- `start = mem_h & 0x07ffffff`;
- `stop = mem_l & 0x07ffffff`;
- the upper five bits of each word carry metadata;
- bit 27 of the low-bank word is tested as the tag bit;
- the exact full maximum-power reconstruction is not asserted by F303 because
  the optimized instruction schedule does not prove the final combined store.

The pointer wraps in the hardware ring. Pulse timestamps and derived widths/PRI
therefore use modulo `2^27`, matching `RADAR_PULSE_MASK` in `detect.h`.

## Zero-Crossing Acquisition

The zero-crossing path is directly visible at `0x3f66..0x4116`.

- It snapshots `NEW_MODE_MEM_L_PTR` and `NEW_MODE_START_PTR`.
- The per-poll row count is capped at `18`, matching
  `ZC_TO_READ_PER_POLLING`.
- Each pulse row occupies `0x1c0` bytes in the software matrix.
- It reads 32-bit RAM words and expands four 8-bit samples per word.
- `28` words produce `112` samples per pulse, matching
  `WIN_PER_PULSE=28` and `ZC_PER_PULSE=112`.
- Addresses above `0xe6400dff` are represented as invalid samples.
- The pointer wraps after `0xe6400fff` back into the 4 KiB ZC window.

This establishes acquisition layout, not the chirp decision thresholds.

## Preprocessing

The unnamed function at `0x26e8` is identified as `radar_preprocess` by two
direct calls from the worker and repeated references to the corresponding
`__func__` string.

Its evidenced responsibilities are:

- copy raw 16-byte pulse records into the software history;
- derive width and PRI modulo `2^27`;
- merge/filter pulses using configured width, separation and power bounds;
- preserve tag and maximum-power metadata;
- update raw/processed/read/left/tag/merge/filter statistics;
- return the normalized pulse buffer/count consumed by `detect_radar`.

The full merge policy is not reconstructed as source-equivalent C.

## Classifier Dispatcher

### Batch entry

`detect_radar` is an exported 3580-byte function at `0x95cc`. Its public
prototype is preserved:

```c
bool detect_radar(raw_pulse_t *s, int count,
                  int count_last_window, zc_cb_t *zc_cb);
```

The observable dispatch is:

1. Build a filtered pulse town and candidate center values.
2. Run inlined frequency-hopping and EU-weather/OCAC checks where enabled.
3. If the interleaved path is selected and enabled, call `isit_itlv()`.
4. Otherwise test the candidate directly against SSR pulse-width and PRI
   bounds. The direct bound checks are visible at `0xa202..0xa23c`.
5. Independently, when LSR is enabled, call `lsr_detect()` at `0xa28e`.
6. Record a detection through the unnamed helper at `0x8ef8`.

Stats updates corroborate the classification branches:

- SSR counter: `detect_cb + 75 * 4`;
- ITLV counter: `detect_cb + 76 * 4`;
- LSR counter: `detect_cb + 77 * 4`;
- `detected_lsr_flag`: byte offset `215`.

### Poll-only entry

`detect_radar_poll` at `0x9038` is an LSR continuation path. It returns false
unless LSR is enabled and `lsr_detect_poll()` returns true. On success it
increments the LSR counter, records the event and sets `detected_lsr_flag`.

### ITLV

`isit_itlv` at `0x90a4` is a 1318-byte cluster validator. The binary strings
and branches establish:

- processed pulse and cluster construction;
- up to 18 interleaved entries;
- valid-cluster checks using pulse-width centers and PRI differences;
- true/false result returned to the batch dispatcher.

The exact clustering score and all regional thresholds remain proprietary.

### LSR and chirp

`lsr_detect` at `0xc160` is a 3216-byte state-machine entry. It is supported by
`lsr_detect_poll`, `lsr_detect_init` and `lsr_detect_reset`.

High-confidence inferred helpers are:

- `verify_burst` at `0xa46c`, identified by its `__func__` relocation;
- `are_zcs_linear` at `0xa670`, which performs coefficient-based correlation
  over zero-crossing samples;
- the LSR FSM reset helper at `0xa814`.

`verify_chirp` and `is_it_tone` names are retained in `.rodata` and referenced
inside `lsr_detect`, but the optimizer did not leave independent symbols. Their
logic is therefore classified as inlined/partially mapped, not recovered.

The binary proves counters for chirp detected, rejected and no-information,
plus configurable minimum detections, maximum rejections and frequency
neighborhood thresholds. It does not by itself prove a correct reimplementation
of those tests.

## Callback Conditions

`radar_register()` stores qdrv's callback at `.bss+0x1070`. The only indirect
invocation is at `0x4bbe` inside the polling worker.

The proven control-flow condition is:

```text
detection candidate exists
AND post-detection history/rate gate does not suppress it
AND callback pointer is non-null
    => callback()
```

The raw optimized condition immediately before the call is:

```text
candidate = (r16 != 0)
gate_input = r5 || r2 || (r19 && flag_137b && flag_137a)
noreject_override = (flag_101d != 0)
suppressed = gate_input && !noreject_override
callback = candidate && !suppressed && callback_ptr
```

The semantic names of `r5`, `r2`, `r19` and the four private bytes are not
fully proved. `flag_101d` is high-confidence the `/proc/radar` `noreject`
override because that command writes the byte and a nonzero value bypasses the
suppression branch. The other surrounding strings and proc controls show
pulse-history, rate-filter and rejection-state behavior, but F303 intentionally
retains the raw expression instead of inventing additional field names.

In qdrv, `mark_radar()` contains one action:

```c
qdrv_radar_detected(qdrv_radar_cb.ic, 0);
```

Thus the OEM detector reports a local radar event; qdrv owns CAC, CSA,
evacuation and NOP behavior after that callback.

## F303 Test-Vector Harness

Implemented files:

- `tools/f303_radar_vector_harness.py`
- `tools/test_f303_radar_vector_harness.py`
- `outputs/kernel-port/f303-oem-radar-re-20260904/test-vector-schema.json`
- `outputs/kernel-port/f303-oem-radar-re-20260904/test-vectors/`

The harness provides:

- paired pulse-bank decoding;
- modulo-`2^27` width and PRI normalization;
- tag and high-bit metadata extraction without overclaiming max-power layout;
- FIFO and 18-row ZC polling bounds;
- a dispatcher model driven by explicit OEM-oracle booleans;
- callback/rejection assertions;
- an explicit `classification_algorithm=NOT_IMPLEMENTED` result.

It does not access MMIO, load modules, contact the router or decide whether a
waveform is radar.

## Proposed Oracle Workflow

Future vectors should be collected from an isolated preserved OEM boot or an
authorized RF laboratory, then replayed offline:

1. Record region, channel, bandwidth and exact OEM module hash.
2. Capture paired pulse-bank words and ZC rows before software preprocessing.
3. Capture OEM counters before/after and whether the registered callback fired.
4. Store only sanitized RF vectors; exclude calibration, MACs and credentials.
5. Replay the vector through F303 normalization.
6. Later, run any independent classifier implementation against the same vector.
7. Require exact agreement for class, callback, false-positive corpus and
   false-negative corpus before enabling DFS transmission.

The OEM strings expose a historical `/proc/radar` test protocol using
`tstart`, `tdata:<start> - <stop>` and `tend`. That is evidence for a possible
oracle-input path, not authorization to run it and not proof that it exercises
the physical RF acquisition path.

## Remaining Unknowns

- Complete SSR/FH/ITLV/LSR regional threshold tables and all interactions.
- Exact combined maximum-power field encoding across both pulse words.
- All `check_radar` private-state names and rejection timing semantics.
- Exact OCAC pointer ownership across qdrv, MuC and the host detector.
- Correct 20 MHz IIR/filter behavior; the binary visibly distinguishes 80 MHz
  from an alternate branch but does not prove a dedicated 20 MHz profile.
- False-positive/false-negative performance against regulated radar waveforms.

F303 is therefore an evidence and test-foundation milestone, not a DFS-ready
firmware candidate.
