# F327 OEM-compatible software lifecycle integration

Checkpoint: 2026-09-21. No router, SSH, UART, radio, network, boot, firmware or flash action was performed. No firmware image was created.

F327 now integrates a nonblocking, IRQ-safe request adapter into a new Linux 5.10 ARC provider. It corrects the port's sleeping ABI calls and stale capture/history attribution while preserving the OEM rule that disable does not wait for an already admitted callback. It is an offline integration artifact: active DFS and radar callbacks remain compiled closed.

## Reproducible result

Evidence: `outputs/kernel-port/f327-event-provider-20260921T101312287864Z/manifest.json`.

- Module: `qtn_radar_native_f327.ko`, 58,848 bytes.
- SHA-256: `46b6347387dfd27ba5d998634dd66b5a9debc1746f33f03158d76d5b05020f0c`.
- Vermagic: `5.10.260-openmitrastar-radiohw mod_unload ARC700`.
- Two complete module builds are byte-identical; all 18 radar symbols export.
- Seven lifecycle groups and eight OEM adapter groups pass. The adapter tests compile the same `f327_oem_kernel_adapter.inc` included by the kernel provider.
- GCC static analyzer passes. ASan/UBSan were not run because WSL lacks the linked `libasan.so.8.0.0` and `libubsan.so.1.0.0`; the failed optional link log is preserved.
- F316 classifier copies are hash-identical. A normal SSR result compares byte-for-byte against the unchanged F316 implementation. This proves preservation of F316 behavior for that fixture, not OEM algorithm equivalence.
- Two existing Quantenna header pointer-type warnings remain; there are no modpost unresolved-symbol warnings or stack-frame warnings.

Sources: `work/kernel-port/modules/f327_radar_event_lifecycle/`.
Composition: `tools/compose_f327_oem_adapter.py` deterministically transforms pinned F316 main source.
Build/test: `python tools/build_f327_event_provider_offline.py` creates a fresh evidence directory on every run.

## OEM versus port: the implemented decision

| Behavior | OEM evidence | F316 / early F327 | Final F327 decision |
| --- | --- | --- | --- |
| Set channel | `.text+0xf8` stores one byte and returns. | F316 added a sleeping mutex and changed epoch without resetting classifier history. | IRQ-safe request generation; worker applies new context and resets the real classifier state. Identical channel requests preserve generation. |
| Disable | `.text+0x43c` clears enabled state and calls `del_timer` without joining the worker. | F316 used a mutex; early F327 added universal cancel-sync/drain. | Short spinlock closes admission, nonblocking cancellation, no wait for an already admitted callback. |
| Stop | `.text+0x490` tears down software/timer state. | Early design treated physical quiesce/restore as universal. | Nonblocking stop request. Final module teardown joins the worker in process context before unmapping. No hardware-stopped claim. |
| Callback | `void callback(void)` and qdrv's current channel existed in OEM. | The full-drain design attempted stronger semantics across all qdrv channel publishers. | Preserve that ABI and inherited in-flight behavior; generation checks suppress new dispatch after a newer request. No claim to redesign the original qdrv race model. |
| Set bandwidth | `.text+0x114` stores width and writes the selected IIR bank. | F316 did complete reconfiguration through a sleeping path. | Request is nonblocking; worker owns reconfiguration and publishes readiness only for the applied generation. This asynchronous application still needs physical timing validation. |
| Detector algorithm | Proprietary binary preserved with relocations and symbols. | F316 reconstruction includes conservative/missing branches. | F316 is only the unchanged integration fixture; exact OEM engine work is F328, with callbacks closed until the full input/postfilter contract is ready. |

Direct OEM evidence is `outputs/kernel-port/f303-oem-radar-re-20260904/objdump-dr.txt`, including exported `radar_register`, `radar_set_chan`, `radar_set_bw`, `radar_disable`, `radar_stop` and `radar_enable`. The qdrv callback/context and IRQ/timer paths are also present in `work/sources/Quantenna-GPL/drivers/qdrv/qdrv_radar.c`.

The early requirement to drain every callback before any channel setter was a stronger new design requirement, not demonstrated OEM parity. It is not used to postpone the port or demand a redesign of the whole wireless stack. The historical 60,444-byte and 60,804-byte F327 artifacts are preserved but superseded by the atomic request adapter above.

## Actual runtime structure

`f327_oem_requests.h` holds generation, requested channel/width, registration mask and enabled/started requests. The caller holds one IRQ-safe spinlock. It contains no allocation, mutex, sleep, MMIO or callback invocation.

`f327_oem_kernel_adapter.inc` implements the real ABI request operations. Disable and stop immediately invalidate generation and exposed readiness, then use nonblocking `cancel_delayed_work`. Setters queue work after releasing the spinlock. No IRQ caller executes `cancel_delayed_work_sync` or takes the classifier mutex.

`f327_oem_worker.inc` owns the classifier and the portable lifecycle core. It snapshots requested context, applies a new generation with `f316_classifier_init`, and reserves a capture token before acquisition MMIO. After the BB lock is released it checks that the requested generation still matches, processes the batch, then checks generation again before callback admission. A request arriving during classification prevents a new callback. An admitted callback may finish after disable; the implementation does not label this as a drained or stopped callback.

`f327_event_lifecycle.c` still provides strict ownership inside the single worker: capture/event tokens, duplicate protection, full history reset, exactly-once callback reservation and fault/exhaustion handling. External IRQ setters no longer call that core or wait on its drain protocol.

The final module keeps `F327_RELEASE_QUALIFIED=0`. `radar_start` returns false, the enable adapter cannot activate DFS, and module initialization rejects `authoritative_enable=1` and `weather_enable=1`. This is not an operator-overridable qualification flag. No runtime or RF acceptance is inferred from compilation.

## Why the atomic ABI matters

Source root below: `work/linux510-radio-port/quantenna-v6-scheduler-diag/`.

- **CSA hard IRQ:** `qdrv_mac.c:303` registers the IRQ; dispatch at `203` calls the CSA handler registered by `qdrv_wlan.c:1970`. Its PRE path at `1933` calls `qdrv_radar_before_newchan`; `qdrv_radar.c:1734` reaches provider disable.
- **Scan timer:** `wlan/ieee80211_scan.c:155` registers `scan_next`; `1203/1267` call `change_channel`, which calls `ic_set_channel` at `315`. `qdrv_set_channel` invokes before/on-newchan at `qdrv_wlan.c:1013/1018`.
- **DFS move timer:** `qdrv_radar.c:1071..1084` reaches `sys_change_chan`; its alternate path calls `ic_set_channel` at `768`.
- **OCAC tasklet:** registered at `qdrv_radar.c:2082`, it invokes provider enable at `646`.
- **Sleepable channel work:** `qdrv_wlan.c:1871..1877` is a workqueue path, but that did not make all other entries sleepable.

These paths disprove the early sleeping adapter's compatibility. They do not establish a need to change the inherited nonblocking callback ABI. F327's final request adapter handles the known atomic call sites without sleeping.

`qdrv_set_channel_deferred` publishes `ic_curchan` at `qdrv_wlan.c:1828` before MuC PRE; that ordering predates this port. The exact MuC timing around `pre_notification_tu=10` and `LHOST_PRE_DONE` is not specified by the shared header. A later non-DFS chronology probe may measure it, but it is not newly imposed as a prerequisite to copying OEM behavior.

## Hardware ownership is a separate question

F324's save/quiesce/restore requirement belongs to a reversible experiment that relinquishes ownership or promises an in-place restoration. A permanent OEM-like provider may instead retain the radar block and its allocations from start until reset. No evidence here establishes that the OEM restores radar SRAM on disable. The port must preserve reset/calibration ordering and callback/shared-parameter lifetime; it must not invent an inverse register transaction or call quiet counters proof of hardware stop.

F327 reports software state only. Its module teardown drains the Linux worker before unmapping; it does not claim to halt the autonomous producer or restore registers/SRAM. No physical lifetime or RF test has been performed.

## Remaining DFS work and reuse

The qdrv policy implementation already contains 70/600-second CAC, 1,800-second NOP, occupied-block propagation and MUST_STOP_TX evacuation. F316 adds useful control scripts and source-contract tests. These should be reused rather than replaced from memory.

Remaining implementation/parity gaps include:

- F316 `context.history_reject` and `lsr_history_reject` are zero-initialized without the full OEM producers. Its weather/chirp policy is conservative. Enabling those paths does not prove parity.
- Correct FIFO/zero-crossing chronology and the original preprocessing output contract still need evidence. The F328 engine's third argument is `prior_window_count`, not automatically `raw_count`.
- The F328 ABI uses 16-byte raw pulse records and a 21,956-byte ZC object with `49 x 112` signed samples plus accuracy/padding. Its clock input is monotonic nanoseconds converted to legacy HZ=200; Linux 5.10 jiffies at HZ=100 must not be passed as equivalent.
- The current F328 engine reports a candidate, with `postfilter_applied=false` and `callback_authority=false`. It cannot yet replace the complete OEM post-detection gate.
- Width-stable NOP bookkeeping and fail-closed response to a detector failure need explicit verification against OEM qdrv behavior. Existing qdrv source presence alone is not acceptance.

Next concrete integration is a versioned worker-side bridge to the reviewed F328 engine, after proving preprocessing/history counts and ZC ownership against executable OEM vectors. Call its engine only after releasing BB and from the worker's sleepable context. Preserve start/reset/end generation semantics, keep candidate-only results separate from final callback authorization, and do not alter the current sealed F326 image or executor.

Physical acceptance remains separate: captured input under meaningful RF stimulus, detector decisions, CAC TX suppression, radar evacuation, NOP retention/expiry, weather channels, management stability and real client traffic. F327 supplies a tested porting mechanism; it does not claim those gates passed.
