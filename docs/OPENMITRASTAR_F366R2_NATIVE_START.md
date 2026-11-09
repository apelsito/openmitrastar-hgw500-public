# F366r2: invoke and verify the native radar start

2026-09-22. **PASS_OFFLINE_F366R2_NATIVE_START_IMAGE**.
Physical native acquisition remains unaccepted until root executes the new
image and its exact F365 return. No hardware access was performed by this
implementation agent.

## Cause of the first F366 acquisition failure

The root-owned campaign
`/workspace/OpenMitraStar/f366-acquisition/f366-acquisition-20260922T095127Z-2149c8c9/result.json`
returned `FAIL_F366_WITH_F365_RETURN`. The twenty provider observations showed
`ipc_session=1`, `ipc_state=1`, but `started=0`, `hardware_dirty=0`,
`hardware_ready=0`, `request_generation=1`, `applied_generation=0`,
`pm_attempts=0` and no completed jobs. The watchdog ARM handshake succeeded.

F366's ladder loaded the provider and attached its userspace engine, but never
issued `radar enable eu`. In the actual qdrv source, `qdrv_radar_init()` only
prepares callbacks/timers. The call to native `radar_start()` belongs to
`qdrv_radar_enable()`, whose only caller is `qdrv_command_radar()`.
The existing sequential command guard also rejected any mutation after the
single AP VAP, so adding a shell command alone would have failed admission.

The native ladder returned zero; the controller then rejected the zero job
progress. The parser's old `native_start_failed` label for any OMF366_ERROR
line must not be read as proof of an earlier ladder failure. This is a missing
native startup integration, not evidence of a sensor, calibration, provider
hardware or F338/F341 marker failure.

## Minimal correction

Only `qdrv/qdrv_control.c` changes relative to the F366 qdrv source. A new
read-only-at-runtime module parameter,
`openmitrastar_native_radar_diagnostic`, defaults to zero and has mode0400.
The r2 diagnostic loader passes it as1.

The exception requires the completed sequential core and single VAP, exact
command `radar enable eu`, actual AP role, channel36 and bandwidth80. It
consumes the single attempt before entering the OEM void API, including on
startup failure. Disabled profile, wrong region, extra arguments, disable/off,
invalid context and retry remain rejected. All other command restrictions and
the permanent F355 lifetime remain intact.

The native loader enters a new `native-radar` phase with a30-second limit and
checks a live watchdog HEALTH acknowledgement before that command. It verifies
actual `started=1` and `hardware_dirty=1`. IIR programming and the first job are
asynchronous after callback registration, so it waits at most five seconds for
`hardware_ready=1` and `jobs_completed>0`, checking HEALTH and engine errors.
It never repeats the enable command. The normal controller independently rejects
an unstarted/untouched provider before collecting twenty observations.

The two additional host-safe markers are:

```text
OMF366_NATIVE_START_ATTEMPT command=radar-enable-eu authority=0
OMF366_NATIVE_STARTED started=1 hardware_dirty=1 hardware_ready=1 authority=0
```

Helpers, proc path, provider ABI and marker names intentionally remain F366.
The firmware product/build distinguish r2. Authority remains compiled off,
channel36/BW80 remains the only diagnostic profile, the supervisor remains the
exact F365 binary, and the absolute session limit remains180 seconds.

## Immutable image and recovery

Private directory: `f366r2-f365-native-start-device-bound/`.
Image: `openmitrastar-linux510-f366r2-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH.webformat.bin`.

| Property | Value |
| --- | --- |
| Bytes | 5,451,776 |
| SHA-256 | `c260249e2633e6e90b775ea51c25b68b1771ff3f340f54f652ef967e83fcbb07` |
| Manifest SHA-256 | `d37225c0493bb59ffb7820ddb625e65d1356f7e494843a38a6c17e8ad0cf9132` |
| Product | `lyoko-foundation-6.10.3-f366r2-native-start-diagnostic` |
| Build ID | `d5e4b5ea094491dd` |
| Prefix CRC32 | `652a807d` |
| Full slot CRC32 | `64db5015` |
| Full slot SHA-256 | `da13ca9a651f8e2c883435becf3ed6cb1dfa80f4cc19180abc66b5079a47bb8d` |
| Bootbase / slot fit | PASS / PASS |
| Space before store | 708,608 bytes |

Private build result:
`analysis/f366r2-fullimage-20260922T101619Z/result.json`.
It supplies the fifteen exact runtime path/hash bindings for the physical runner.

The fallback stays exact F365, SHA-256
`43f4655f09eb01d749ca24c003689470b2f7c2d2738333297348e965e56d5355`,
full-slot CRC32 `118901d4`; the preserved sequence2 journal is CRC32 `5d2ee646`.
Kernel, DT, Ethernet, 2.4 GHz, watchdog, temperature, calibration, credentials,
identity and protected partitions are unchanged by this composition.

## Offline validation

- `/workspace/OpenMitraStar-build/f366r2/f366r2-components-20260922T101129Z/result.json`:
  two identical builds, 41 actual installed modules, 1,977 resolved imports and
  no dependency/GPL-only/taint conflicts. Original fourteen qdrv parameters are
  unchanged; only the named0400 diagnostic parameter is added. The protected
  lifetime, temperature and WPS functions are byte-equivalent.
- qdrv is690,872 bytes, SHA-256
  `eb8f9c45d15881c79dc89e412d593f6bd8fcde5cd7137e40dc213496a6b23ca4`.
  Provider and userspace engine are byte-identical to F366.
- `outputs/preflight/f366r2-start-gate-20260922T101019Z/result.json`:
  22 checks execute the actual qdrv admission and handler bodies, including
  rejected profile/order/arguments/context/retry cases.
- `outputs/preflight/f366r2-runtime-20260922T101504Z/result.json`:
  28 shell checks and actual F340 IPC with six phases and fake watchdog/radio.
  A regression recreates a successful ladder with an unstarted provider and
  verifies rejection before the observation loop.
- `outputs/preflight/f366r2-readback-20260922T101600Z/result.json`:
  actual loader handshake block with asynchronous first job, never ready,
  invalid job count and never started fixtures. Every case issues one command.
- Two independent full repacks are byte-identical. Complete inventories and
  catalogues pass. The former F365 qdrv hash appears nowhere in the new rootfs;
  the current qdrv hash is bound exactly in the private loader, driver contract
  and radio catalogue.

These checks are offline evidence. Acquisition, RF detection, CAC, evacuation,
NOP, real client traffic and release acceptance require their physical gates.
F367 remains unpromoted until corrected native acquisition and recovery pass.
