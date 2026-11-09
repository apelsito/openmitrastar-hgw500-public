# F324 radar lifecycle: transaction core, hardware adapter blocked

Checkpoint: 2026-09-19 CEST (2026-09-18 UTC).

The owner requested the DFS acquisition lifecycle correction and flash with
`go a eso y a flash`. Implementation was started under that instruction.
There is no flashable F324 image: the hardware stop/ownership prerequisite is
unresolved. This is a technical NO-GO, not a request to repeat the owner's GO.
No router, UART, radio, boot environment or firmware was changed by this work.

## Verified result

The new portable transaction core builds for the existing ARC700 toolchain.
Its stateful device model passes 21 cases covering both original producer
states, each acquisition failure, partial writes, stop/restore/readback
failures, repeated calls, and retention of ownership/checkpoints after failure.
Two ARC object builds are byte-identical; no undefined imports remain.

- Sources: `work/kernel-port/modules/f324_radar_lifecycle/`.
- Builder: `tools/build_f324_radar_lifecycle_offline.py`.
- Final evidence:
  `outputs/kernel-port/f324-radar-lifecycle-20260918T233732959647Z/manifest.json`.
- Artifact: `libf324radar-lifecycle.a`, 1,750 bytes, SHA-256
  `f36c90b22f24dae9e84c2b0aedfa261cf8d23dd4907f4d15af7fe930c81a5716`.
- Classification: `PASS_OFFLINE_TRANSACTION_MODEL_NO_GO_FIRMWARE`.

The artifact is a static library, not a kernel module, firmware image, hardware
adapter or physical validation. ASan/UBSan were not run: the initial compiler
attempt could not link the distribution's sanitizer runtime libraries. That
failed attempt is preserved separately. The final model was compiled with
`-Wall -Wextra -Werror -pedantic` and executed successfully without sanitizers.
Sealed F315/F316/F321/F322/F323 sources and images remain unchanged.

## Transaction implemented

1. Acquire exclusive ownership; a failed acquisition must have no side effects.
2. Save original controls before a stop operation changes them.
3. Stop the physical producer and verify the stop.
4. Save capture memory only after verified quiescence.
5. Configure, read back, start, and independently verify activation.
6. On stop or a partial start failure: stop and verify the producer again,
   restore saved memory and controls while stopped, and verify the checkpoint.
7. Restore the original producer state, verify it, then release ownership.

Any failed recovery retains ownership and the checkpoint in
`F324_RECOVERY_REQUIRED`. No force-release/reset shortcut is exposed.
The backend must keep its private checkpoint until successful release.
Calls must be serialized and bounded by the eventual hardware adapter; a
kernel deadline/worker integration is not implemented by this portable core.

## Why the QT4 adapter cannot yet be implemented as a passing physical gate

The current F322 guard explicitly reports `NO_GO_ARM_CLEANUP_CONTRACT`.
Its pinned F315 source hash was verified unchanged:
`4844a097957ceb8e735de223e57c7843bc34c36247a68b6289c2a59367f09d33`.

| Evidence | What it proves | What it does not prove |
| --- | --- | --- |
| F315 `f315_configure_hardware`, lines 376-424 | Configuration writes, interrupt acknowledgement, pointer resets and capture-memory clearing occur | An inverse transaction exists |
| F315 worker, lines 538-572; exit, lines 876-882 | Disarm skips polling; exit cancels the worker and unmaps | Hardware capture stopped or original registers/SRAM restored |
| GPL `qtn_bb_mutex.h`, lines 52-77 | `qtn_bb_mutex_enter` acquires a reader reference shared with other readers | Exclusive capture-producer ownership |
| GPL `qtn_bb_mutex.h`, writer/reset helpers | A software writer can exclude compliant readers during a critical section | The autonomous radar producer is halted; the writer helper is a bounded session lease |
| OEM `radar_disable` at `.text+0x43c` and `radar_stop` at `.text+0x490` | Software state/timer teardown | A documented capture-hardware disable/restore sequence |
| OEM `radar_proc_write` at `.text+0x5170..0x51b2` | The RX option writes a masked 0/1 value to `0xe60914d4` | `0` stops all capture; the header name is not a hardware stop specification |

OEM disassembly source:
`outputs/kernel-port/f303-oem-radar-re-20260904/objdump-dr.txt`.
Register declarations:
`work/sources/Quantenna-GPL/drivers/radar/radar.h`.
Do not copy GPL/OEM images, calibration or credentials into public evidence.

A reversible hardware adapter still needs evidence for:

- an ownership protocol excluding other configuration writers across the
  transaction, including cross-processor users;
- a bounded stop command and an actual hardware acknowledgement that capture
  cannot write SRAM (quiet counters alone do not establish this);
- the legal read/write/restore semantics of each register: interrupt-clear,
  pointer, command and read-to-clear registers cannot be blindly replayed;
- capture-memory access while halted, plus safe resume ordering;
- a bounded session/deadline, concurrency handling, and recovery if any
  checkpoint restoration step fails.

These callbacks remain absent. No unverified register write is hidden behind a
successful simulated callback. Synthetic success does not lift the physical
gate. Flashing the static library, relabelling old F322, or installing an inert
image would not close this blocker.

## Next physical boundary

Use documented QT4 semantics or a separately designed, single-variable physical
probe to establish a stop/acknowledgement before integrating the adapter.
Any such probe must declare its hypothesis, exact changed register/mask, source
provenance, meaningful stimulus, bounded exposure, rollback and inconclusive
outcome. A lack of pulses cannot be labelled successful quiescence.

Once the adapter and recovery are qualified, build a new immutable full image
with its exact hash/size, Bootbase contract and original F321/F314 recovery
artifacts. Revalidate device/UART ownership and protected/current-slot readback
before the authorized flash workflow. Existing F323 approvals are scoped to
F323 and do not identify a future DFS image.

The next candidate must still boot non-DFS with capture disarmed. Detector
classification, CAC/TX suppression, radar evacuation/NOP, weather support,
client traffic and final release remain separate gates.
