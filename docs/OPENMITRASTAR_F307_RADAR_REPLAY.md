# OpenMitraStar F307 Deterministic Radar Replay

Date: 2026-09-04

## Classification

- Scope: offline evidence and state-machine replay only.
- Native RF detector: NOT IMPLEMENTED.
- Physical radar detection: NOT PROVEN.
- F302 module load: NOT RUN.
- Router, AELITA, UART, TFTP, flash and MTD: NOT USED.
- Flash candidate: NOT PRODUCED.

## Purpose

F307 turns the F303 single-vector decoder into a deterministic timeline replay.
It joins three independently evidenced contracts without pretending that the
proprietary classifier has been reconstructed:

1. F303 decodes paired pulse words and models the OEM dispatcher from explicit
   oracle booleans.
2. The preserved qdrv state machine supplies CAC, transmit suppression,
   evacuation and NOP behavior.
3. The Lyoko ES policy supplies complete 20/40/80 MHz occupied-channel blocks,
   70-second standard CAC, 600-second weather CAC and 1800-second NOP.

The result is suitable for replaying future sanitized OEM observations and for
regression-testing a later independent classifier. It is not suitable for
selecting or transmitting on a DFS channel.

## Files

- `tools/f307_radar_replay.py`
- `tools/test_f307_radar_replay.py`
- `outputs/kernel-port/f307-radar-replay-20260904/session-schema.json`
- `outputs/kernel-port/f307-radar-replay-20260904/fixtures/`

## Replay Contract

Every session pins the preserved OEM radar SHA-256, explicitly records that raw
UART and sensitive material were not retained, normalizes country `ES` to the
OEM radar region `eu`, and provides a monotonic event timeline.

Supported replay events are:

- backend start and detector enable;
- CAC start and completion;
- F303 pulse-vector poll;
- transmit-allowed probe;
- channel switch;
- NOP probe;
- backend stop.

A poll never derives a radar class. The embedded F303 vector contains the
observed or synthetic oracle outputs. Only an oracle-driven
`mark_radar_callback_fired=true` registers radar, aborts CAC, blocks transmit,
requires evacuation and starts a 1,800,000 ms NOP.

## Included Fixtures

### Standard CAC

Channel 100 at 20 MHz. Transmission is blocked before 70 seconds and admitted
only after the complete CAC. The synthetic oracle reports no classifier hit.

### Weather CAC

Primary 116 at 80 MHz occupies 116/120/124/128. Because the occupied block
intersects the weather-radar interval, transmission remains blocked for the
full 600 seconds.

### Radar During CAC

A synthetic ITLV oracle hit at 10 seconds fires the modelled callback, aborts
CAC, registers channel 100 in NOP, requires evacuation and keeps transmission
blocked. Switching to immediate channel 36 restores modelled transmission. NOP
is verified active at 1,809,999 ms and expired at 1,810,000 ms.

## Fail-Closed Checks

- `ES` without `eu` normalization is rejected.
- 40 MHz requires an explicit valid secondary channel.
- 132/136/140 at 80 MHz are rejected because channel 144 is absent.
- CAC completion one millisecond early fails.
- Polling without an enabled detector fails.
- A target channel in NOP cannot be selected.
- Sensitive keys such as PSK, passwords, client MACs or calibration are rejected.
- Every result states `classification_algorithm=NOT_IMPLEMENTED` and
  `physical_rf_detection_proven=false`.

## Future OEM Oracle Input

After a separately authorized OEM oracle capture, construct a session with
`source=oem-oracle-sanitized`, the exact sanitized capture SHA-256 and one or
more F303 vectors containing the observed OEM counters and callback result.

The replay result must be stored next to the immutable capture. Later native
classifier candidates can consume the same pulse/ZC input and must match the
OEM oracle class, rejection decision and callback behavior before any physical
DFS gate is considered.

Synthetic replay proves serialization, timing and state transitions only.
Calibrated RF testing remains mandatory for detector sensitivity, false
positives, CAC monitoring, evacuation timing and regulatory acceptance.
