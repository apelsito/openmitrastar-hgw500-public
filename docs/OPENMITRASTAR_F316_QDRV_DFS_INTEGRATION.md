# OpenMitraStar F316 qdrv DFS Integration Contract

Date: 2026-09-05

## Result

The Linux 5.10 `qdrv` DFS control plane is sufficiently complete to accept an
external radar provider through the preserved Quantenna radar ABI. The provider
must not merely call `mark_radar`: it must satisfy the lifecycle, channel and
failure contracts below because several provider calls have no return value and
several return values are ignored by `qdrv`.

This is a source audit only. No `qdrv` source, module, firmware, radio, UART or
MTD state was changed.

Audited sources:

- `work/linux510-radio-port/quantenna-v6-scheduler-diag/qdrv/qdrv_radar.c`
  - SHA-256: `c261b6777d9322a4baf641a37861bf588e754e5411f7f993ea16725d00c395dc`
- `work/linux510-radio-port/quantenna-v6-scheduler-diag/qdrv/qdrv_wlan.c`
  - SHA-256: `f4def5f050cb8500efdd12103839c606a1641fef11e808734ce93beeeafb00fa`
- `work/linux510-radio-port/quantenna-v6-scheduler-diag/wlan/ieee80211_input.c`
  - SHA-256: `0a9fe5e65d41cdfcc13cdbf063673935c79bfd082726067cf354f06a00cb4c45`

## State Ownership

`qdrv` owns the DFS policy state:

- whether DFS is configured and enabled;
- whether the operating role is DFS master or slave;
- DOTH gating;
- TX stop/start through `qdrv_hostlink_xmitctl()`;
- CAC timers and `CAC_IN_PROGRESS` / `CAC_DONE` flags;
- NOP timers and `IEEE80211_CHAN_RADAR` flags;
- channel availability for the complete occupied 20/40/80 MHz block;
- CSA, scan and channel selection after detection.

The external provider owns radar hardware and detector truth:

- QT4 setup and teardown;
- current detector bandwidth and primary channel;
- acquisition, preprocessing and classification;
- detector enable/disable state;
- exactly-once delivery of a validated detection through the callback registered
  by `radar_register()`.

The callback has type `void (*)(void)` and carries no channel, width, timestamp
or class. Therefore a callback is valid only while the provider's configured
channel and bandwidth still match the current qdrv context.

## Provider ABI Contract

### Start

The first `qdrv_radar_enable(region)` performs:

```text
radar_start(region)
  -> radar_set_bw(ic->ic_radar_bw)
  -> radar_disable()
  -> radar_register(mark_radar)
  -> radar_register_is_dfs_chan(...)
  -> radar_register_is_dfs_weather_chan(...)
```

`radar_start()` is the only startup operation whose result controls qdrv
initialization. It must return `true` only when all of the following are true:

1. the region is recognized and its detector profile is installed;
2. QT4 mappings and detector state are valid;
3. the worker can be started and stopped safely;
4. `detect_drv_sample_loc_get()` will return a stable non-NULL object;
5. all callback registrations will succeed;
6. later `radar_set_bw()`, `radar_set_chan()`, `radar_enable()` and
   `radar_disable()` can satisfy this contract.

On any partial failure, `radar_start()` must unwind its own resources and return
`false`. It must remain disabled and must never call the callback.

The provider must accept region `es` through the EU/ETSI detector profile while
`dfs_rqmt_code("es")` reports `DFS_RQMT_EU`.

### Enable, disable and channel updates

- `radar_set_bw(bw)` must synchronously install a complete 20, 40 or 80 MHz
  profile before returning.
- `radar_set_chan(chan)` must update the classification context before a later
  `radar_enable()` can produce a callback.
- `radar_enable()` must publish `radar_get_status() == true` only after the
  detector is fully armed.
- `radar_disable()` must synchronously prevent new callbacks before returning
  and must publish `radar_get_status() == false`.
- `radar_stop()` must stop the worker, synchronize any callback already in
  flight, release mappings and leave the detector disabled.
- Calls must be idempotent. Repeated enable/disable operations must not duplicate
  workers, lose ring ownership or deliver stale detections.

Because qdrv ignores the return from `radar_set_chan()` and does not verify the
result of `radar_enable()`, either operation failing requires the provider to
remain fail-closed and expose failure through its own status/telemetry. F316's
runtime supervisor must then stop the 5 GHz service; it must not call
`qdrv_radar_disable()` as a fail-closed shortcut on a DFS channel because that
function explicitly re-enables TX.

### Callback

The provider may invoke the registered callback only when all conditions hold:

- startup and all registrations completed;
- detector status is enabled;
- the snapshot is internally consistent and belongs to the active channel and
  bandwidth;
- the classifier accepted a complete radar event;
- the event was not already delivered for the same acquisition epoch;
- disable/stop is not in progress.

The provider must invoke it from sleepable or deferred context compatible with
the qdrv path. It must not invoke it while holding the baseband/MMIO lock because
the callback can stop CAC, change channel state, send CSA and disable detection.

The callback path is fixed:

```text
provider callback
  -> mark_radar()
  -> qdrv_radar_detected(qdrv_radar_cb.ic, 0)
  -> validate configured/enabled/ic/DFS context
  -> mark NOP
  -> disable detector for in-service detection
  -> select and evacuate to another channel
```

`qdrv_radar_detected()` calls `stop_cac()` before it validates the complete
detection context. A false or stale callback can therefore abort a valid CAC.
The provider is the mandatory debounce and stale-event barrier.

## DOTH, CAC And TX Contract

Radar detection is required only when both are true:

```text
IEEE80211_F_DOTH is set
AND
the current channel carries IEEE80211_CHAN_DFS
```

The debug override `QDRV_LF_DFS_DONTCAREDOTH` is test-only and must be disabled
in a release image.

Before entering a DFS channel, `qdrv_radar_before_newchan()` stops MuC TX and
disables detection. After the channel is installed, `qdrv_radar_on_newchan()`
sets the provider channel and follows this state machine:

| Channel state | Required action |
| --- | --- |
| Non-DFS | enable TX, disable detector |
| DFS with valid OCAC result | mark available/CAC done, enable TX, arm detector |
| DFS master requiring CAC | keep TX blocked, start CAC, arm detector |
| DFS already available | enable TX, arm detector |
| DFS slave strict mode | apply the strict STA CAC policy |

CAC duration is selected from the complete occupied block:

- standard DFS: `70 * HZ`;
- EU weather-radar intersection: `600 * HZ`;
- quick `30 * HZ` mode is test-only and forbidden in release.

At CAC start, qdrv sets `CAC_IN_PROGRESS` across the occupied block and keeps TX
blocked. At successful expiry it enables TX, sets `CAC_DONE`, clears
`CAC_IN_PROGRESS`, marks the block available and retains in-service monitoring.
Radar during CAC cancels CAC, leaves TX blocked, starts NOP and enters the DFS
action path.

## Detection, Evacuation And NOP

For an in-service AP detection:

1. duplicate detections already marked with `IEEE80211_CHAN_RADAR` are ignored;
2. an optional board callback may consume the event by returning zero;
3. `IEEE80211_FEXT_MARKDFS` must be set;
4. DFS test mode must be off;
5. `start_nonoccupy()` marks the channel and schedules NOP;
6. detection is disabled to suppress redundant callbacks;
7. qdrv chooses the configured alternative, another usable channel, or a
   non-DFS scan result;
8. CSA enters with `IEEE80211_CSA_MUST_STOP_TX` and reason DFS.

The default NOP is exactly 1,800 seconds. At expiry the complete occupied block
becomes `NOT_AVAILABLE_CAC_REQUIRED`: radar flags and prior CAC completion are
cleared, so reuse requires a new CAC.

If no usable evacuation channel exists, the contract is fail-closed: TX must
remain stopped and userspace must surface `csa_fail`. F316 must not treat the
absence of a destination as successful evacuation.

Off-channel CAC detection marks NOP for the off-channel block but deliberately
does not evacuate the current non-DFS operating channel.

## Occupied 20/40/80 MHz Blocks

The block, not only the primary 20 MHz channel, is the unit of DFS state.
`qdrv_mark_channel_availability_status()` and
`qdrv_mark_channel_dfs_cac_status()` expand the primary channel using the
current PHY bandwidth and the HT40/VHT80 position flags.

| Width | Occupied entries | Required propagation |
| --- | --- | --- |
| 20 MHz | primary | availability, radar, CAC flags |
| 40 MHz | lower + upper | availability, radar, CAC flags on both |
| 80 MHz | LL + LU + UL + UU | availability, radar, CAC flags on all four |

`qdrv_check_channel()` rejects a candidate when any occupied subchannel carries
`IEEE80211_CHAN_RADAR`. Weather CAC is selected when the occupied 40/80 MHz
block intersects a channel flagged `WEATHER_40M` or `WEATHER_80M`.

Only one NOP timer is created for the primary entry that received the event;
expiry propagation is recalculated from the then-current PHY width. Until this
is replaced with a width-stable NOP record, F316 must forbid bandwidth changes
while any NOP is active. Otherwise expiry could clear a different block from
the one originally marked.

## Known Failure Modes

- **FM-01 registration-result blindness:** qdrv ignores the three
  `radar_register*()` return values. `radar_start()` must pre-prove registration
  viability and the provider must never advertise readiness after partial setup.
- **FM-02 enable-result blindness:** `radar_enable()` returns `void`; qdrv does
  not confirm that arming succeeded before continuing.
- **FM-03 channel-result blindness:** `radar_set_chan()` returns an `int`, but
  qdrv ignores it in both new-channel paths.
- **FM-04 callback ambiguity:** `mark_radar(void)` contains no channel or epoch;
  stale callbacks can be attributed to the current channel.
- **FM-05 early CAC cancellation:** `qdrv_radar_detected()` stops CAC before
  validating DFS applicability, OCAC context or duplicate state.
- **FM-06 disable re-enables TX:** `qdrv_radar_disable()` ends by enabling TX.
  It is an administrative disable path, not a DFS failure-containment path.
- **FM-07 width-dependent NOP expiry:** occupied-block propagation uses current
  width at expiry instead of preserving width at detection.
- **FM-08 no-destination evacuation:** a NULL channel produces `csa_fail` but
  the qdrv branch itself does not issue a second explicit TX stop.
- **FM-09 sampling dependency:** the first enable requires a VAP and a non-NULL
  detector sample object; failure occurs after `radar_start()` and after
  `qdrv_radar_first_call` is cleared.
- **FM-10 optional interception:** `qw->radar_detect_callback(chan)` returning
  zero consumes the event before MARKDFS, NOP and evacuation.

## F316 Acceptance Contract

F316 may activate the external provider only when all of these are proven:

1. all 18 external radar ABI symbols link without `qdrv_radar_compat.o`;
2. startup is atomic and all register/enable/channel operations are observable;
3. disable/stop synchronizes the worker and callback;
4. DOTH-off and non-DFS operation never produce a callback;
5. standard and weather CAC keep TX blocked for 70 and 600 seconds respectively;
6. a callback during CAC aborts CAC, creates NOP and never enables TX;
7. a callback during operation starts NOP and enters MUST_STOP_TX evacuation;
8. 20/40/80 MHz tests mark, reject and expire the complete occupied block;
9. NOP lasts 1,800 seconds and reuse requires CAC;
10. duplicate and stale detections are suppressed;
11. every failure leaves 5 GHz TX stopped while Ethernet, SSH and 2.4 GHz stay
    available;
12. quick timers and DFS test overrides are absent from the release profile.

The accompanying `tools/test_f316_qdrv_dfs_contract.py` is a read-only source
contract. It proves that the audited Linux 5.10 tree still contains the qdrv
state transitions described here. It does not prove physical radar detection.
