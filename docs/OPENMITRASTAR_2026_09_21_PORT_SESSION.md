# HGW port session â€” 21 September 2026

## Latest installed baseline: F340 after successful F346

Run `outputs/handoff-live/f346-install-20260921T151945Z-f4aa6c0b/` completed
`PASS_F340_PERSISTENT_WATCHDOG_BASELINE`. Exact F340 (5,349,376 bytes) was
installed only in the mtd4 prefix, compared byte for byte and read back with
full-slot CRC `2aa26ca6`. Protected partitions and store CRCs are unchanged.
The new F340 boot and DT marker are verified; platform passes 27/27. Watchdog
is available, inactive, EN=0, counter=0xffff, ready for explicit owner use.
No ARM, DFS acquisition or Wi-Fi/client test occurred. No rollback was needed.

Tool session 20321, outer PID 29428 and parent PID 5752 are complete. UART,
helpers, lease and process-local awake hold are closed. F340, not F321, is
the current running image. Cold-power-cycle acceptance remains distinct.

Further completed offline artifacts are indexed at the top of
`AGENT_CURRENT_MISSION.md`: F341 DFS image, F342 4 KiB journal, F344 vendor
supplicant, F345 serial packet encoder and F347 passive-control rebuild.
F344 full mode integration and F348 common flash-reader arbitration continue.
F345 does not yet implement the real controller transport. A text question
about the actual flash marking is pending; both candidate parts share the
JEDEC ID but have distinct individual-protection protocols.

The automatic review rejected F343 deliberate CPU-stop preparation. No such
test or module was executed/created; do not repeat or disguise the trigger.
The owner explicitly deferred Wi-Fi/RF/client tests and AELITA access. Continue
ordinary port work within those limits, without claiming full release parity.

## Latest recovery and executable results at 13:38 UTC

F336 attempt 2 transferred and booted the RAM kernel, but its marker command
used absent `tr`, so identity timed out. Root read-only SSH observed #336 and
the inactive Topaz DesignWare watchdog; no experiment ARM occurred. The
return then failed because renewed autoboot interception replayed old UART
events and exhausted its event limit. Its immutable `FAILED_UART_CAPTURE`
result is `outputs/handoff-live/f336-ram-20260921T132233Z-03826f49/result.json`.

A fresh owned UART observation confirmed ZHAL without reboot/flash. A separately
bound direct recovery then read and CRC-checked F321, validated iminfo and
bootargs, and booted it once. Evidence:
`outputs/recovery/f336-bootbase-20260921T133521Z-9177a1ee/result.json`.
Platform acceptance is **27/27 PASS** at 13:37:22 in
`platform-verified/status.json`. A prior host argument error before SSH is
preserved in `platform/invocation-failed.json`; it is not a hardware failure.
All helpers/UART/lease/awake holds are closed; session 79776 ended.

The F336 probe executes on real ARC with expected negative inspection under
F321: `outputs/handoff-live/f336-probe-negative-20260921T133802Z/`.
The final F338 service executable (75,212 bytes) also passes all 398 math
selftest checks: `outputs/handoff-live/f338-ram-math-20260921T133822Z/`.
Neither check opened UAPI/watchdog or changed radio/flash; RAM cleanup passed.

The owner explicitly deferred Wi-Fi tests and does not want AELITA connected.
No more AELITA requests/access or Wi-Fi/RF/client tests; implementation continues.
The current agent split is F339 internal temperature/hwmon plus F336 runner
fixes (`hardware_parity_inventory`), F340 persistent watchdog baseline
(`dfs_core_audit`), and F341 complete DFS image integration against F340
(`watchdog_linux510_port`). F340/F341 remain offline preparation and do not
inherit physical acceptance from compiled components. Root alone operates HGW.

## F336 first attempt returned F321 at 13:20 UTC

`outputs/handoff-live/f336-ram-20260921T131641Z-9e5f6ff2/result.json`
records FAIL at `ssh_deadline`: reboot reached fresh Bootbase, while the
old SSH client remained open. The controller treated that expected teardown
timeout as failure before accepting the UART proof. It then read F321 from
flash, checked prefix CRC `bd1135df` and full-slot CRC `6ed8e483`, and booted
it directly. No diagnostic RAM boot, watchdog arm or flash write occurred.

The exact returned baseline passes 27/27 in `return-platform/status.json` at
13:20:28 UTC. UART capture and child containment passed, the parent released
the lease, session 8831 ended and the process-local awake request ended.
The original result remains failed. F336 sources are unfrozen for a targeted
fix: terminate the old SSH client within its deadline, then accept reboot
only from a fresh UART prompt after the request. A silent UART still fails.

A separate read-only attempt to the historical AELITA client at 192.168.1.63
timed out: `outputs/handoff-live/wifi-oracle-readonly-20260921T131147Z/`.
No Wi-Fi/client configuration changed. An asynchronous question asks the
owner to leave AELITA connected or supply its changed address; this does not
block ongoing kernel/DFS implementation or the RAM watchdog test.

## Real ARC/Linux math acceptance at 13:06 UTC

The corrected immutable F338 userspace selftest passes on the physical F321:
`outputs/handoff-live/f338-ram-math-20260921T130615Z/result.json`.
Both bounded binaries exit zero; the engine passes 398 checks including 55
classifier vectors and both empty-window reset boundaries. No UAPI/MMIO was
opened. Same F321 boot and removal of all staged RAM files are confirmed.
This is real Linux math execution, not DFS RF/acquisition acceptance.

The original 13:04 failure remains immutable below. Its cause was the harness
expecting reset at prior count 100, whereas the OEM oracle resets above 100.
The new harness verifies count 100 remains valid and 101 requests reset.

## Implementation checkpoint at 13:05 UTC

F321 remains the stable physical baseline. No UART or firmware operation is
active. Root executed only two RAM userspace checks after recovery:

- `outputs/handoff-live/f338-ram-math-20260921T130402Z/result.json`: the bounded
  Linux control executable passes; all 55 classifier vectors complete, but the
  new combined selftest fails at preprocessing check 393 (exit 30). The OEM
  oracle requires the empty-window reset at a prior count greater than 100;
  the harness incorrectly expected reset at 100. Preserve this FAIL, correct
  the harness to cover both boundaries, and test a new immutable executable.
  No UAPI/MMIO was opened and all staged files were removed.
- `outputs/handoff-live/f335-status-compat-20260921T130439Z/result.json` passes
  the negative status compatibility contract on the actual old F321 daemons:
  2g reports unsupported with control disabled; 5g reports control unavailable.
  Same F321 boot verified, staged helper removed, no WPS session started.
  This proves status compatibility only, not WPS enrollment.

The F332 all-kernel integration is NO-GO: actual Linux 5.10 module-loader
license/taint rules reject its proprietary OEM math dependency together with
GPL-only kernel imports. No such bundle has been loaded. F338 retains hardware,
lifecycle, postfilter and qdrv control in GPL kernel code and moves the exact
OEM math into a bounded ARC userspace engine/UAPI. Do not relabel licenses or
bypass the loader. Its full integration is in progress.

The hardware agent is preparing an executable F336 RAM-only watchdog test,
using the corrected F321 partition DT, continuous UART and a separately bound
direct F321 read/boot return. The core agent is reviewing startup writes and
F338 loss-of-provider TX/CAC handling. Root remains sole physical operator.

## Fresh F321 recovery completed at 12:05:21 UTC

The owner power cycle recovered a new pristine F334 boot. The reviewed fresh
recovery then restored exact F321 and passed platform 27/27 plus its original
UI/authenticated HTTP checks. Evidence:
`outputs/recovery/f334-after-reset-20260921T120202Z-fd02977b/result.json`.
Status: **PASS_EXACT_F321_RESTORED_AFTER_FRESH_RESET**. Full F321 byte comparison,
slot CRC and protected partitions are verified in its `restore/` directory.
Permission was unchanged; helper containment and lease release passed.

Root session 61745 and awake-helper session 71236 ended successfully. No write,
UART owner or hardware campaign is currently active. F321 is the current
verified installed image; F334 capture failure remains historical evidence.
Next work: native DFS/WPS integration, and RAM-only watchdog validation with
continuous UART evidence before another unproven acquisition attempt.

## F334 access recovered after the owner power cycle

The owner confirmed the requested power cycle. Pinned SSH now identifies a
new F334 boot (`0206117b-ccea-4543-8437-7260972115c0`). At uptime 102 seconds
boot/radio5 state became ready; the earlier degraded state at 34 seconds was
transient. A subsequent read verified once_phase, hardware_dirty, shadow_arm,
configured, poll_runs, config_attempts, mmio_writes and callback count all zero.
No new capture has been requested. Evidence:
`outputs/handoff-live/f334-pristine-after-power-20260921T115322Z/result.json`.

F334 is still installed. The separately qualified fresh F321 recovery runner
is being prepared with a real F334 nonce and a new lease; no stale binding is
relabelled as F321. No write or hardware campaign is currently active.

## Historical F334 capture stop before that power cycle

The campaign at `outputs/flash-watch/f325-ethernet-20260921T113155Z-ea9253f2/`
ended in **STOP_NO_AUTOMATIC_RETRY** at 11:39:29 UTC. F334 write/readback and
platform 27/27 passed. Capture failed after `arm_attempted=true`; only the
PRE-arm observation exists. Actual arm/MMIO completion is unknown.

The automatic F321 return **failed at reboot before its writer/transfer**.
The last verified flash remains F334, not F321. The reboot UART log is empty
and a subsequent root SSH check timed out. No process is currently writing:
all monitored helpers are contained, lease released and parent PID 5532 ended.
Root command session 24671 and awake-helper session 59030 have both completed.

The user has been asked to power-cycle only the HGW, retaining USB/UART and
Ethernet. Do not repeat the consumed F334 launcher or arm again blindly.
After a genuinely new clean F334 boot, a separately qualified fresh recovery
wrapper will restore exact F321 using a new lease and SSH/UART binding.
Never copy/forge the old borrowed guard. The owner's existing recovery and
flash authorization remains applicable; fresh hardware evidence is required.

Parent records are in `outputs/launchers/f334-executor-20260921T111605Z/`.
The execution review remains
`outputs/preflight/f334-executor-20260921T111605Z/ethernet-executor-review.json`.
The earlier F326 campaign below successfully restored F321, but that is an
older outcome and must not be presented as the current installed state.


The owner requests complete OEM functional parity on Linux 5.10 before
improvements, explicitly authorizes flash and requests unattended execution.
The current operator is the root agent. Subagents must not access the device.
Preserve protected partitions, immutable firmware and evidence, and exact
F321 return. A later physical result supersedes this checkpoint only with its
own evidence; this document does not authorize skipping any integrity gate.

## Physical campaign completed at 10:49:15 UTC

Final result: `FAIL_F325_EXACT_F321_RESTORED`. The executor family is still
called F325; the image actually installed in this run was F326. Its write and
readback passed, but platform acceptance failed at `beacon-preflight-readback`
with radio5 stopped and no capture armed. Kernel/SSH/2.4 GHz remained available.
The parent then restored exact F321, verified its full-slot CRC `6ed8e483` and
all 5,337,088 candidate bytes, and obtained platform **27/27 PASS**.

The final outer result proves unchanged existing permission, zero firewall
changes, no privilege request, helper containment and lease release. Both root
tool sessions 37924 (campaign) and 24689 (temporary host awake hold) have ended.
No hardware action is currently running from this campaign. The one-use
launcher remains consumed; do not retry the unchanged F326 image.

Root launched the qualified existing-permission executor once at 10:37:04 UTC.
Its single-use claim has been consumed. The immutable evidence is:

`outputs/flash-watch/f325-ethernet-20260921T103704Z-59134aab/`

Parent records:
`outputs/launchers/f326-existing-permission-20260921T102102Z/parent-started.json`
and later `parent-result.json`. Parent PID at start: 23332. The root tool session
is 37924; file evidence is authoritative if the tool session is unavailable.
The plan installs exact F326, captures once and restores exact F321. It must
revalidate the current device/UART, permission, backup and readback gates.
Starting the parent is not evidence of flash or capture success.

The subsequent `verified-writer.json` now records **F326 write/readback PASS**:
5,320,704 candidate bytes compared, full-slot CRC32 `53bea2a4`, prewrite F321
CRC32 `6ed8e483`, and protected-partition CRC verification true. Hardware
SHA-256 remains unmeasured. The later terminal evidence above proves the F321
return. The F326 capture was never reached; no acquisition PASS may be inferred.

Latest review:
`outputs/preflight/f326-existing-permission-20260921T102102Z/ethernet-executor-review.json`,
SHA-256 `20e42447195850c657447c1030f0d7b9dde5ef09677439b4842ad0c885e033a8`.
685 tests pass, 86 source files are frozen. The launcher SHA-256 is
`49af210121609518a475ebd261eb4edd3afc57b758ca46d9bf4b587bb9eb76a0`.
There is no UAC request or firewall mutation in this mode.

## Live baseline and host

Pinned F321 identity: `outputs/handoff-live/dfs-resume-readonly-20260921T095128Z/result.json`.
Platform 27/27: `outputs/handoff-live/dfs-platform-20260921T095423Z/status.json`.
F321 version `lyoko-foundation-6.8.5-f321-classic-ui-f314-device`, build
`ad60c8e1e49dfbbf`; kernel `5.10.260-openmitrastar-radiohw`.
Read-only SSH after the synthetic client still found the same kernel and zero
selected kernel fatal markers. These observations preceded the completed
physical F326/F321 campaign described above.

Actual PC link: `Ethernet`, Realtek Gaming GbE Family Controller,
interface **18**, `192.168.1.49/24`. Interface 17 is VirtualBox, not the old
physical link. COM3 retains the expected FTDI identity.

## Existing Windows permission is sufficient for the measured UDP path

The normal launcher requested elevation once; it ended without starting at
10:01:34 UTC. The error and absence of a physical attempt are preserved under
`outputs/launchers/f326-network-20260921T0953Z/`.

Root then inspected an existing, enforced Windows **Allow** rule for the exact
Python312 executable, UDP, Public profile. No rule was changed. Rule name:

`UDP Query User{B53A0DF9-DAAE-4615-9572-87C57A3EF67B}/workspace/user-home\appdata\local\programs\python\python312\python.exe`

Python SHA-256:
`4d6f5f81a4bca11191c4c7c6b43632694d0a4ce74e068619d8fdc161d469859a`.
Its existing filters allow UDP with any ports/addresses on Public; the
application server still restricts the transfer to the HGW and one file.
The permission is not created by this project and must not be removed at cleanup.

The actual synthetic path proof is
`outputs/preflight/f326-existing-tftp-probe-20260921T102246Z/result.json`, SHA-256
`b09b2bd92c098c0a0833453a4c29670bcc08c7c7c14b4db506dc130281c6edbf`.
It reports `PASS_TFTP_WITH_EXISTING_PERMISSION`: 4,096 pattern bytes, nine ACKs,
zero retries, both sides successful, sockets closed, RAM-only client removed,
and identical permission snapshots before and after. It transfers no firmware.
The client verifies every pattern byte. This does not prove a complete Bootbase
transfer or replace its RAM CRC/readback gate.

Probe sources: `tools/probe_hgw_existing_tftp_path.c` and `.py`.
The first result (`...102101Z/`) remains FAIL because the client returned no SSH
exit status after the acknowledged transfer. Replacing stdio/finalization with
direct write and `_exit` produced the passing second result; exact libc root
cause is not proved. No failed report was rewritten.

The executor is being adapted to an explicit **existing-permission** mode with
fresh read-only validation of this rule, program hash, interface and profile.
That mode must perform no administrator check, RunAs, firewall creation or
firewall removal. It uses already granted permission; it must not evade an OS
denial, silently fall back, or weaken device/lease/readback/recovery checks.
The 645-test review at `outputs/preflight/f326-network-20260921T0953Z/` qualifies
the earlier managed-rule mode only. Require the new review for changed sources.

## Implemented offline components

- F327: real IRQ/timer-compatible provider adapter, generation-bound acquisition
  and history reset; 15 deterministic groups and reproducible ARC module.
  `docs/OPENMITRASTAR_F327_SOFTWARE_LIFECYCLE.md`.
- F328: exact OEM classifier bytes, 1,008 relocations, explicit legacy facade;
  six real ARC/QEMU vectors, 159 facade checks and 12 adversarial acceptance
  tests. Reproducible proprietary Linux 5.10 engine, 51,184 bytes, SHA-256
  `211945065d75e7b4929c550c571d5ba9d54aebdfde77730f4309a39ffbc4cc49`.
  `outputs/port-parity/hgw500-20260921T095258Z/F328_EXACT_OEM_ENGINE.md`.
  OEM HZ is **200**, F321 HZ is **100**; the engine converts monotonic time to
  OEM ticks. It does not apply the missing postfilter or authorize callbacks.
- F329: Topaz adaptation of Linux 5.10 DW watchdog, complete isolated kernel
  build; 25 driver C cases, two restart fallback cases and nine contracts pass.
  `docs/OPENMITRASTAR_F329_WATCHDOG_PORT.md`. Device tree remains disabled;
  actual timing and reset are not physically accepted.

F330 now has 24 passing OEM/QEMU preprocessing cases and a reproducible
23,668-byte kernel engine, SHA-256
`b566b28a7e6da502497afc40a1d4c5e8ca005135dd3c0aa82650f9b728e19a584`.
Use its actual final result and `docs/OPENMITRASTAR_F330_EXACT_OEM_PREPROCESS.md`
as authority for the artifact binding. It preserves two windows, 32-bit
timestamps, up to 128 raw/256 processed pulses, and explicit pending reset
acknowledgement. Reset thresholds count preprocessing calls, including flushes.

F331 has 5,360 comparisons against exact OEM postfilter bytes, 460 native
assertions, and a reproducible 5,148-byte kernel component, SHA-256
`a73a10ed48e35f888b12566e5bacbc17e3a215cb53d42f8dc54e484075424d74`.
Its documentation records the corrected rate input as **tx_bytes per second**,
not packets. See `docs/OPENMITRASTAR_F331_POSTFILTER_PORT.md`.

F332 composes these components with the F327 lifecycle and new OEM engine
wrapper. Its arithmetic pipeline has run against both OEM objects in QEMU;
the real provider/backend and composed firmware remain separate gates.
F333 is validating acquisition/RAW/ZC decoding against original instruction
slices. Do not infer hardware acceptance from these emulated fixtures.

F334 corrects the failed diagnostic qdrv profile. The F315/F326 donor lacks
`OPENMITRASTAR_QDRV_V89_PAIR`, exposes only `tqe_sem_en`, and compiles the beacon
preflight getter to return zero. F321 has the required parameters and actual
readback `Y`; see `outputs/handoff-live/f321-qdrv-parameters-20260921T105345Z/`.
The new external-radar build preserves the canonical F321 profile and uses
the exact current kernel configuration. The inherited sysfs 0700 warning is
not the missing-beacon-parameter cause. Do not repeat unchanged F326.

F335 builds the same pinned 2.4 GHz hostapd sources with WPS support. Two builds
match under `outputs/kernel-port/f335-hostapd-wps-20260921T110353Z/`:
hostapd 620,284 bytes (`9d4339e59814163277bf08aa4894f7d0c3ea4a01c726973b6b11d0c8edbef5644`)
and hostapd_cli 58,484 bytes. Use that directory's `result.json` for exact hashes.
Startup/control integration and physical enrollment remain pending; WPS has
not been activated on the device. The first build's failed qualifier expected
the wrong timeout event; it remains preserved separately.

These are new implementation tracks, not installed firmware. Do not substitute
zero for unresolved OEM inputs or treat a classifier candidate as a validated
radar event.

The full parity inventory is
`outputs/port-parity/hgw500-20260921T095258Z/PARITY.md` with hashed `sources.json`.
It separates this videobridge's real functions from generic DSL/ONT/voice
features not demonstrated on this device. Persistent configuration, OEM radio
modes/WPS, both Ethernet paths and on-board peripheral acceptance remain in scope.

## Continuing agent ownership

- Root remains the only physical operator. F321 is restored; no campaign is
  currently running at this checkpoint. The next proposed physical image is
  the F334 once-capture diagnostic, after its new executor review is qualified.
- `dfs_core_audit` now owns F334 qdrv profile correction, image reproduction
  and exact existing-permission executor rebinding. F327 is already complete
  offline. Do not infer this agent's current work from its old name.
- `watchdog_linux510_port` now owns F332 integration of F327/F328/F330/F331/F333.
  F329 watchdog and F331 postfilter are complete offline. F332 must preserve
  original clock/cadence, real sample units and explicit unsupported contexts.
- `hardware_parity_inventory` now owns F335 WPS control/startup integration.
  F328, F330 and F333 have their own final evidence. F335 hostapd binaries have
  already been built by root; use their canonical result rather than rebuilding
  or changing the sealed output directories.

The F326 failure's primary cause is the donor qdrv compilation profile, not
corrupt flash or absent Windows permission. F334 uses the canonical F321
profile with external radar imports and the exact installed kernel headers.
The source-identical WPS read function legitimately gets corrected signal
structure offsets from those headers; do not force stale offsets to reproduce
an old binary hash. Preserve the comparison evidence and label the difference.
