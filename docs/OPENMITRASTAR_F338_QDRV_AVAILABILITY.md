# F338 qdrv: detector availability loss and recovery

Offline implementation completed 21 September 2026. No router, UART, RF, TFTP,
flash or module-load action was performed. F334 firmware and its 86-source
executor, the fresh F321 recovery runner, and F332 source/artifacts are preserved.

## Qualified artifact

`outputs/kernel-port/f338-qdrv-availability-20260921T132134Z/manifest.json`
records two byte-identical ARC/Linux 5.10 builds:

- `qdrv-a.ko`: 686,736 bytes, SHA-256
  `73a5b9c889880a301fcca58711fee298f0819897be1a12076a7c090c3dd745d4`.
- `qdrv-a-Module.symvers` is the qdrv export table for integration.
- All 14 parameter names/permissions and the functional beacon-preflight
  helper match the verified F334/F321 profile.
- Sixteen behavioral C groups compile the exact readiness and availability
  helpers; three further cases compile the actual qdrv teardown function.
- Twenty-four source-order/lifetime checks and GCC static analysis pass.
- Imports resolve against the 22-function F338 provider ABI. The module depends
  on `qtn_radar_f338`; it does not import the proprietary detector engines.

Builder: `tools/build_f338_qdrv_availability.py`.
Versioned source: `work/linux510-radio-port/quantenna-f338-availability/`.
Only `qdrv/qdrv_radar.c`, the new `qdrv/qdrv_f338_availability.inc`, and
`tests/test_ready.c` differ from the F332 qdrv snapshot. The existing F332
readiness helper is reused unchanged. The three original profile macros remain.

## Availability contract

The provider registers a separate callback through
`radar_register_availability(void (*cb)(uint32_t generation, uint32_t reason))`.
This callback is not the OEM radar-detected callback.

| Reason | Meaning of generation | qdrv action |
|---|---|---|
| 1, service closed | Last published continuity, or zero before first READY | Invalidate detector-dependent service |
| 2, service timeout | Last published continuity | Same loss action |
| 3, service protocol error | Last published continuity | Same loss action |
| 4, hardware fault | Last published continuity | Same loss action |
| 5, service READY | Current newly published nonzero continuity | Re-enter readiness/CAC, never enable TX directly |

The provider calls outside BB, request and provider state locks, in workqueue
context. It immediately removes READY when loss is detected and does not
publish replacement READY while its loss notice is pending/in flight. qdrv
also rejects stale notices when a different generation is already READY.
Duplicate loss/READY notifications do not restart deadlines or valid CAC.

## Loss while operating

For a DFS service, loss first closes TX admission and invalidates CAC/OCAC
generation tokens. Outside spinlocks, qdrv forces an XMITCTL OFF operation,
nonblockingly cancels CAC, and clears completed/in-progress CAC and OCAC flags
for the affected current/CAC/scan channels. Accumulated OCAC dwell and any open
OFF_CHAN interval are discarded. Non-DFS service does not require the detector
merely because an off-channel CAC is interrupted.

No loss path invokes `qdrv_radar_detected`, `mark_radar` or `start_nonoccupy`.
An existing radar/NOP availability state is preserved. READY recovery cannot
start CAC or admit TX on a channel still blocked by a real radar/NOP decision.
The tests use the actual OEM availability macro, including its implicit local
`ic` and channel-availability callback, rather than treating radar state as
only a channel flag.

XMITCTL can block in process context. The code never holds a spinlock across
it. TX enable checks admission before sending and again after completion. If
loss or shutdown overtakes an already admitted enable, the completing path
forces OFF even if the loss callback had already sent an earlier OFF command.
This closes the late-enable ordering race without adding a sleeping lock to
IRQ callers.

An unconfirmed hostlink stop sets a persistent qdrv fault latch and denies
re-enable. It does not report `xmit_stopped=true` based on a failed operation.
An enable failure also forces OFF and latches the fault. Actual radio emission
and hardware stop latency still require physical validation.

## Recovery and CAC completion

The inherited readiness retry runs every 50 ms for at most five seconds.
Timeout leaves TX blocked. A genuine reason-5 READY can re-enter that gate
after a later daemon restart, including first startup after the retry expired.
Opening the device or merely receiving an unverified message is insufficient.

After loss, a full CAC on the new generation must complete before the health
latch permits TX. An old CAC completion cannot clear it. A duplicate READY for
an already running valid CAC does not restart that interval. Completion now
publishes its channel state before TX admission; a concurrent loss can invalidate
that state and the final admission check remains authoritative. The existing
70/600-second CAC and 1,800-second NOP timers are unchanged.

## Lifetime and evidence limits

The availability callback is registered only after qdrv radar timers, OCAC
tasklet and control state are initialized. Registration failure uses the normal
teardown path. Full teardown closes/joins readiness work, drains qdrv timers,
then calls the provider's process-only `radar_wait_stopped` before clearing ic.
That provider API joins both poll and availability work and removes the stored
callback. No synchronous join is added to an IRQ or availability callback.

The initial failed builds remain in timestamped directories: they exposed a
Linux `current` macro collision and the OEM availability macro's implicit `ic`
dependency. Both were corrected; the final harness reproduces the latter.
Intermediate passing binaries are not the final artifact named above.

This qualifies source, ABI linkage and deterministic software behavior. The
integrator must still verify the complete GPL provider/userspace bundle and
its peer-module imports. Kernel loading, actual service-close recovery, CAC
silence, channel evacuation, RF classification and release acceptance are not
claimed by this qdrv-only offline result.
