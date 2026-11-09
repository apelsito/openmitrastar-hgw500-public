# F325 single-boot QT4 acquisition experiment

Date: 2026-09-19. Target: HGW-500BNA-QCv2 A2, 192.168.1.90.

## Final checkpoint at 01:04 UTC

F321 is running, with pinned SSH identity confirmed again at 01:04:24 UTC.
The full platform gate passed 27/27 at 00:51:13 UTC after UART recovery.
**F325 has not been written to flash and capture was never armed.**

Two Ethernet attempts both transferred 5,320,704 bytes with zero retransmissions
but stopped before the writer: first on the progress backspace, then on the
vendor's `(0xhex)` transfer-count format. All original STOP results remain
unchanged. The second attempt's C0 metadata observed exactly one backspace.
The expected vendor formats are independently confirmed in the local U-Boot
sources; the failed transfer's numeric line was not stored as raw text.

The host now accepts only the documented progress decoration and the two exact
numeric formats, including `filesize=0x...`. The F325 backend applies one
checked regex transformation to the hash-pinned F321 source; F321 itself is
unchanged. Source review of subsequent iminfo/CRC/memory-display formats found
no additional required compatibility change.

Final qualification and reproducible preparation:

- UART/backend/context/UI: **165 PASS** in
  `outputs/preflight/f325-executor-adaptation-20260919T0012/uart-qualification-v2.xml`.
- Ethernet/capture/numeric parsing: **578 PASS** in
  `outputs/preflight/f325-executor-adaptation-20260919T0012/ethernet-qualification-v5.xml`.
- Final review:
  `outputs/preflight/f325-executor-adaptation-20260919T0012/ethernet-executor-review-v3.json`,
  SHA-256 `6dabbde21d43fb509dd4acdea23c425e59c7be61a49202e13cac5717bc9f03d3`.
- All 81 reviewed execution sources are copied and hash-checked in the
  adjacent `final-source-snapshot/` directory.
- File-only final plan: adjacent `final-plan.json`,
  `OFFLINE_READY_FRESH_PHYSICAL_GATES_PENDING`.
- Last actual router identity:
  `outputs/recovery/f325-final-readonly-20260919T010423Z/result.json`.

The owner requested unattended work and went to sleep. The device was recovered
to F321 and remaining work was completed offline. A new unproven capture was
not started without the hard-halt/power-cycle contingency available. The
existing owner GO is retained; offline readiness does not establish physical
acceptance or remotely controlled power recovery.

The working UART recovery and the empty-line command-repeat trap are documented
in [Bootbase prompt recovery](OPENMITRASTAR_BOOTBASE_PROMPT_RECOVERY.md).

This is the owner's requested diagnostic flash, one capture window and return
to exact F321. It is an alternative to the blocked F324 in-place hardware
restoration design. It does not unlock DFS channels or claim a working radar
detector, CAC, NOP or final radio acceptance.

## Immutable image

- Directory: `/workspace/user-home/.openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f325-f321-radar-once-device-bound`.
- File: `openmitrastar-linux510-f325-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH.webformat.bin`.
- Size: 5,320,704 bytes.
- SHA-256: `98a08807df84feb6c7d3cc8081a6bc92a64e5f472e0dc269bc52232e6089b126`.
- Candidate RAM CRC32: `5bf57eae`.
- Full-slot expected CRC32: `e53660ed`.
- Firmware version: `lyoko-foundation-6.9.3-f325-radar-once-f321-device`.
- Firmware build: `53f1ee3368f3b27f`; preserved UI build: `72dd5d1877544af9`.
- Kernel, DTB, credentials and unrelated rootfs metadata remain unchanged.
- Bootbase and slot-fit pass. Independent second composition matches image,
  rootfs, full-slot, kernel, DTB, config and complete metadata inventory.
- Reproducibility evidence:
  `outputs/preflight/f325-shadow-repro-20260919T001705Z/result.json`.

The module retains the F315 module/ABI name to use the unchanged, hash-pinned
external qdrv consumer. Its source is versioned separately under
`work/kernel-port/modules/f325_radar_once/`, and its status explicitly reports
`lifecycle=f325-single-boot-reset-required`.

## Diagnostic behavior and limits

The image boots in ES/channel 36/80 MHz, acquisition unarmed. There is no
automatic arm at boot. A reviewed host gate must verify the installed files,
live physical lease, actual WEXT radio profile and pristine counters first.

One arm is allowed per boot. Before configuration can write hardware, the
provider records `hardware_dirty=1` and pins its own module until reboot. It
never registers or invokes radar callbacks and keeps DFS authority denied.
Normal radio configuration transactions are locked in this diagnostic image;
the regular radio-stop helper refuses a dirty capture state.

The worker checks a 20-second SOFTWARE deadline. Success requires observing
the autonomous stop (`once_phase=2`, `shadow_arm=0`, `polling=0`,
`stop_reason=2`) and stable final counters. A manual stop must never prove the
autonomous deadline. Empty batches remain inconclusive; nonempty batches
prove acquisition activity only, not correct physical radar classification.

**This is not a hard hardware watchdog.** The inherited BB semaphore/MMIO path
can block or panic before the next deadline check. `cancel_delayed_work_sync`
cannot interrupt a wedged hardware operation. The owner's confirmed access to
power and the bound UART is the hard-halt contingency. No concurrent qdrv
unload/reinitialization is allowed: pinning the provider does not pin qdrv's
shared-parameter allocation. No hardware quiesce or SRAM restoration is claimed.

## Execution and recovery

The Ethernet campaign uses the current PC source 192.168.1.249, Ethernet index
17, verified COM3/FTDI identity and authenticated SSH-to-console binding. It
does not change host IP addresses/routes, persistent boot environment or boot
selection. The temporary firewall rule is scoped to this run/program/peer and
must be removed afterward. Windows elevation is required for that rule.

Only physical `mtd4/linux_live` is written: offset `0x007e0000`, erase prefix
`0x005e0000`, slot size `0x007a0000`. Protected mtd0/1/2/3/5 and the store tail
are preserved. Logical MTD views are not physical write targets.

After a verified F325 write and pristine postboot checks, the parent runs the
single capture and restores exact F321 under the same held lease/firewall.
Capture failure or no pulses does not skip restoration. A failed restoration
is not retried. Ambiguous loading/writing or uncontained processes produce STOP
before any chained write. There is no automatic F314 fallback.

Exact F321 return image:
`eb8e23ac75ec50e113cd337e9b68ab86e366a09c8dbbec255a3b426843a9da18`,
5,337,088 bytes, expected full-slot CRC32 `6ed8e483`.
Physical proof uses full-slot CRC32 and complete candidate-byte comparison;
do not report the locally calculated slot SHA-256 as a hardware measurement.

If the device hard-halts, the automatic cycle may be unable to enter Bootbase.
Keep the original failure evidence and use the owner power-cycle contingency
with a fresh reviewed recovery operation. A working mtd3 safety boot is not
assumed.

## Evidence and current gate

- F325 module: two equal builds and existing pulse-core/new once-policy tests
  in `outputs/kernel-port/f325-radar-once-20260919T000320492832Z/`.
- UART writer/context/UI qualification: 141 passed in
  `outputs/preflight/f325-executor-adaptation-20260919T0012/uart-qualification.xml`.
- Ethernet baseline qualification: 439 passed in
  `outputs/preflight/f325-executor-adaptation-20260919T0012/ethernet-qualification-v2.xml`.
- The first Ethernet run's 39 failures are preserved; stale copied source pins
  and a stale PASS after failed planned recovery were corrected.
- Three user-requested subagents reviewed module/flash behavior and fixed the
  live radio-profile reader. The autonomous-deadline acceptance test is being
  tightened before final qualification.

The final review above now binds the corrected capture source/tests, parent
timeout and all passing behavioral checks. Fresh device/lease/recovery gates
remain prerequisites for execution. No sealed image or earlier report is to
be rewritten to mark physical success.
