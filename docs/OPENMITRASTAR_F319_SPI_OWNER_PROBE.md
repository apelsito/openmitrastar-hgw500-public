# OpenMitraStar F319 SPI controller owner probe

Date: 2026-09-05; latest physical acceptance: 2026-09-07 19:29 UTC.

## Current accepted milestone

Exact F319 is installed on HGW and its claim/map/unload gate is physically
accepted. The final post-probe platform gate passed at 19:29:44 UTC, with pinned
SSH, both radios ready, protected UI/API and no fatal markers. The module is
unloaded and has no autoload. See the final dated section below for evidence.
Earlier NOT_RUN statements in this chronological record describe earlier
checkpoints, not the current result. This is not a SPI transaction-provider,
DFS, new client-traffic, cold-power-cycle or full-release acceptance.

Subsequent F320 review (2026-09-07): this accepted reservation at `0xe4030000`
does not prove that the bus decodes at that address. OEM configuration and the
F319 DTB select the legacy layout, whose SPI base is `0xe2000000`. The kernel
can return an ioremap pointer without touching hardware. Keep the original
claim/map/unload evidence, but do not infer correct address decoding or
electrical arbitration from it. See `docs/OPENMITRASTAR_F320_SPI_CONTROL_READ.md`.

## Purpose

F319 is the first replacement for the unsafe direct-MMIO observer path rejected
in F310. It is a claim-only ARC700/Linux 5.10 module: it reserves the exact
Topaz SPI controller resource and creates a kernel mapping, but it never reads
or writes that mapping.

- Module: `qtn-topaz-spi-owner-probe.ko`
- Bytes: `6,108`
- SHA-256:
  `79436442b62110351fba44262a05ae0f2a9ffc87b36fabe74cc651112e431317`
- All imports resolved against the exact F314 kernel lineage: PASS.

The module is packaged without autoload in a versioned F314-derived diagnostic
image:

- Candidate bytes: `5,292,032`
- Candidate SHA-256:
  `e33d851106aa342509184ab0d1d94fc0654d7206cb2a4c62c5fab7aa48c0dcc9`
- Full-slot CRC32: `22d3802a`
- Full-slot SHA-256:
  `ad8bd328147e9fb03715b258bb99c69bbf0daa3b9c6a4dc993c0365ef7665601`
- Kernel, DTB and radio payload: byte-identical to installed F314.
- Candidate eligibility and guarded `mtd4` flash support: enabled after the
  complete offline module, image and runtime-gate review. Release eligibility
  remains false.

## Contract

- Exact machine gate: `mitrastar,hgw-500bna-qcv2`.
- Controller resource: `0xe4030000 + 0x00010000`.
- Exclusive `request_mem_region` ownership required.
- MMIO reads: zero.
- MMIO writes: zero.
- SPI opcodes: zero.
- MTD devices: none.
- F318 transaction provider: unavailable.
- Autoload: disabled.

The read-only module parameters expose whether the resource was claimed and
mapped. Access counters remain fixed at zero. If another kernel component owns
the resource, module initialization returns `-EBUSY` without touching the
controller.

## Boundary

This is an offline packaged diagnostic and has not been loaded on hardware. It
does not make persistent storage available. Its future physical gate must use
the exact versioned `mtd4` image above, load the module with UART recovery
available, verify claim/map status and zero access counters, then unload it.
Only a later version may add a single bounded read transaction.

Offline physical-plan preflight: PASS at
`outputs/preflight/f319-spi-owner-claim-20260905T160843Z/plan.json`. The plan
pins the exact F314 source, F319 candidate and module hashes, requires UART and
both rollback paths, and records `hardware_actions_performed=false`.

`tools/run_f319_spi_owner_probe.ps1` is the guarded post-install runtime gate.
Its default dry-run and static safety tests pass. Execute mode requires the
exact acknowledgement `OPENMITRASTAR_F319_SPI_OWNER_CLAIM_E33D8511`, pinned
SSH identity, the pinned FTDI PnP identity, an authenticated HGW-to-UART console
nonce and the shared physical lock. It waits for the RX-only UART capture to be
ready before performing one module load/unload, requires both access counters
to remain zero, and compares the MTD table and fatal count before/after. It has
no flash, MTD-write, SPI-opcode, radio-change or reboot command.

`tools/promote_f319_mtd4_direct.ps1` is the corresponding guarded promotion
entrypoint. Its dry-run validates the exact candidate, full-slot hashes,
current F314 rollback identity, protected-partition policy and the disabled
autoload contract. Execute mode requires the exact acknowledgement
`OPENMITRASTAR_F319_MTD4_E33D8511`, writes only physical `mtd4/linux_live`,
and now acquires the shared physical lock plus both session-local FTDI mutexes before
opening the serial device. A console nonce must bind the authenticated F314
host to that UART before any SysRq byte is sent. The guard remains held through
the normal post-flash platform gate and UART-backed F319 runtime probe. The
matching F319-to-F314 rollback uses the same pre-reboot binding. The execute
paths have not been run.

The original bounded regression covering the guard, promotion, rollback and
runtime gate is `10/10 PASS`. It proves source ordering and dry-run behavior,
not the runtime semantics of the guard. The 2026-09-06 behavioral correction
below adds actual Windows process and synchronization tests. Physical board
binding and F319 claim/map/unload remain `NOT_RUN`.

## Host guard corrections — 2026-09-06

The offline audit reproduced an array-construction bug: the two intended mutex
names were concatenated into a single name. Both the parent guard and capture
now construct the two exact, independent names. The namespace is Windows
session-local (`Local`), not a guarantee of exclusion across login sessions or
uncooperative software.

The parent guard now holds `owner.json` open with write/delete sharing denied,
alongside both mutexes. The lease records the process ID, original process start
time, a per-run token and pinned adapter identity. A delegated probe/capture
verifies the live process, exact lease, actual file-sharing conflict and both
held mutexes. A directory, copied JSON, reused PID or command-line bypass flag
alone cannot authorize the child. The capture rechecks the lease before opening
the port, every heartbeat and before completion. This is cooperative local
resource coordination, not proof of which PCB is connected.

The runtime probe now requires a complete capture from its exact run ID and
capture PID, zero gaps/errors, RX-only settings, a successful process exit and
matching nonempty raw/text data. Unique console begin/end markers must bracket
the probe in order. Missing logs, an early/failed capture or a reconnect no longer
count as a clean UART result. The earlier authenticated HGW console nonce remains
mandatory before runtime actions.

SSH scripts are now sent as LF-normalized standard input to `sh -s`, preserving
POSIX quoting independently of Windows argv parsing. Calls are time-bounded;
timeouts are failures with unknown device outcome, not automatic retries. The
capture command line also uses explicit native argument quoting. Guard cleanup
is nonrecursive and preserves unexpected files instead of removing a directory
tree.

Behavioral suite: `tools/verify_f319_offline_guards.py`. Its six matrices use
synthetic adapter IDs, stubbed serial enumeration, temporary files and real
child processes under Windows PowerShell 5.1 and PowerShell 7. They cover 78
cases: live/dead/copied/released ownership, contention, cleanup, complete and
corrupted capture evidence, argument quoting, LF stdin, nonzero exits and
timeouts. No serial port, SSH connection, promoter or physical probe is invoked.
Evidence is under `outputs/preflight/f319-offline-guards-*/result.json`, with
exact source hashes; the objective audit rejects stale hashes.

The candidate and module hashes above remain unchanged. No new firmware was
built or installed by these guard corrections. Existing authorization for the
exact F319 candidate remains granted; no renewal was requested.

### Remaining recovery limitation

`rollback_f319_to_f314_mtd4.ps1` currently requires a working, authenticated F319
SSH session to emit its fresh console binding nonce. It is therefore a guarded
rollback from a functioning F319 runtime, **not** an SSH-dead automatic recovery
path. The promotion wrapper reports failures and releases its guard; it does not
silently run an automatic rollback. Loss-of-management recovery and the manual
Bootbase/safety route still need their own verified physical contingency before
the campaign can be described as end-to-end recoverable. Do not remove the
binding check or treat a free COM3 as a recovery identity.

### Pre-erase transport handoff correction — 2026-09-06

The promotion and rollback wrappers previously selected UART/YMODEM after any
failed TFTP backend result in `auto` mode. They now require positive evidence
that the exact attempt stopped during TFTP transfer, before erase/write. A
generic error, timeout or absence of an erase line is insufficient.

Each TFTP attempt has a new, explicit evidence directory and a random host-only
attempt ID. The backend emits the matching abort marker only after exhausting
the transfer retries and recovering the `topaz>` prompt after cancellation. The
transfer function is called exactly once and precedes every erase/write command.
The marker binds the attempt ID, candidate hash and expected current-slot CRC.
It is not sent to the UART peer as a command.

`tools/f319_flash_fallback.py` records and independently revalidates that marker
against both fixed-name logs and their hashes. Automatic handoff requires a
failed TFTP process, exactly one matching marker and nonempty UART evidence;
any erase/write/readback-success indication rejects it. Missing, changed,
duplicated, unrelated or timed-out evidence rejects handoff. Failure after
erase remains a recovery incident, not a transport retry.

`tools/test_f319_fallback_backend.ps1` extracts only the production TFTP receive
function and replaces all I/O with synthetic objects. It tests transfer success,
exhausted transfer with prompt recovery, and lost-prompt failure on both
PowerShell engines. It never invokes the backend entrypoint or a serial API.
The Python tests additionally exercise evidence corruption/replay, both wrapper
branches, and the complete real F319/F314 artifact/backup/Bootbase chain in
**local dry-run** mode. No attempt directory is created by those dry runs.

The combined bounded regression is 42 PASS, recorded at
`outputs/preflight/f319-pre-erase-handoff-20260906/tests.xml`; the Windows
ownership/capture/argument matrices remain 78 PASS with refreshed source hashes
under `outputs/preflight/f319-offline-guards-*/result.json`.

This correction does not implement SSH-dead recovery or reuse an old board
binding as a new physical identity. The fresh authenticated console binding
requirement remains unchanged. No new firmware image was generated, and no
UART, SSH, TFTP service, reboot or flash operation was performed.

### Physical identity/RX readiness — 2026-09-06 23:42 UTC

The owner confirmed the adapter was released from Askey and connected to HGW.
Pinned SSH verified running F314, kernel `5.10.260-openmitrastar-radiohw`,
`BOOT_STATE=ready`, 2.4 GHz `ENABLED`, 5 GHz `ready` and zero fatal markers.
The existing guard acquired both adapter mutexes and the physical lease. Its
authenticated console nonce was received on pinned COM3. The UART was RX-only:
zero transmitted bytes, DTR/RTS disabled, no reboot, flash or module load.
The port and our guard were released after the check.

Evidence: `outputs/preflight/f319-uart-readiness-20260906T234118Z/result.json`.
This establishes historical identity and RX connectivity, not ongoing ownership,
UART TX, Bootbase recovery, continuous probe capture or F319 claim/map/unload.
Fresh ownership and authenticated binding remain required at execution.

The recovery review found conflicting historical documentation. The original
`outputs/uart-live/boot-safety-after-recovery-20260817.log` accepts the safety
kernel checksum but ends in `VFS: Unable to mount root fs`. The stored audit
`outputs/recovery/mtd3-current-evidence-20260901/result.json` explicitly marks
independent recovery `RECOVERY_NO_GO_ROOTFS_MOUNT_FAILURE`. This is historical
evidence, not a current retest; preservation of that partition does not prove a
working rescue system. `tools/recover_to_oem_safety.ps1` is unsuitable for this
campaign: it can issue ATEN and writes bootenv via `saveenv`.

Promotion was not executed. Before flash, verify a no-SSH Bootbase route that
can restore the exact F314 to physical mtd4 without writing OEM/safety or bootenv.
Do not repair mtd3 or remove the identity gate to bypass this prerequisite.

### Interrupted rehearsal and guarded recovery continuation — 2026-09-07

The first real rehearsal reached Bootbase and began transferring the exact F314
to RAM by YMODEM. The task interruption terminated its processes before a
transfer completion result or flash-backend transcript existed. It is not a
recovery PASS. Its unmodified evidence and the archived dead-owner lease remain
under `outputs/recovery/f319-f314-bootbase-rehearsal-20260906T235640Z/`.

At 08:04 UTC a fresh pinned SSH read confirmed F314, Linux 5.10.260 and boot
ready. A new detached rehearsal at 08:12 UTC stopped before UART access because
the pinned FTDI/COM3 was no longer present. Its result is
`outputs/recovery/f319-f314-rehearsal-detached-20260907T081100Z/run/result.json`.
No reboot or flash occurred in that attempt. COM1 is not a replacement adapter.

The SysRq entry helper now reuses the same pinned PnP fallback as the hardware
guard, fixing the case where Windows lists the FTDI in PnP but not
`Win32_SerialPort`. The flash backend additionally checks mtd3's CRC after the
write, alongside mtd0/mtd1/mtd2/mtd5. Neither change writes protected partitions.

The promoter now requires `-RecoveryRehearsalResultPath` in execute mode. The
proof reader checks the exact F314 restore result, required platform checks and
the hashes of its UART/transfer transcripts; an interrupted run is rejected.
Standalone rollback still requires fresh authenticated F319 SSH/UART binding.

A new in-process recovery branch addresses loss of SSH after a completed F319
installation: if its platform/runtime gate fails, the promoter retains the
hardware guard and calls the exact F314 rollback. The borrowed guard must belong
to the same PID/start time, keep its file lease open, and match the original
authenticated F314 console binding and lease token. Cached readiness JSON and
a lease from an ended process cannot authorize this path. Protected board/slot
CRCs are checked again by Bootbase before erase. The parent releases its guard
only after the rollback returns or fails.

This automatic branch is deliberately unavailable for partial or ambiguous
flash failures: it requires the writer to have completed its readback and boot
checks. A hard CPU lockup that cannot respond to SysRq can still need physical
intervention. This is host-side implementation and offline validation, not
physical recovery acceptance; no F319 image has been installed or probe loaded.

Current offline evidence: 74 integration checks PASS at
`outputs/preflight/f319-recovery-integration-20260907T0826/tests.xml`, including
the actual promotion failure branch with all device I/O stubbed. The 78 real
Windows ownership/capture/transport checks PASS with current source hashes at
`outputs/preflight/f319-offline-guards-20260907T082559Z/result.json`.

### Physical F314 Bootbase recovery PASS — 2026-09-07 11:33 UTC

The detached rehearsal completed at `2026-09-07T11:33:02Z`:
`outputs/recovery/f319-f314-rehearsal-detached-20260907T111355Z/run/result.json`.
Its status is `PASS_F314_RESTORE_WITHOUT_SSH_IN_BOOTBASE`. Fresh authenticated
SSH/UART binding and the exclusive live guard preceded SysRq/Bootbase entry.
YMODEM loaded all 5,292,032 bytes of exact F314, with RAM CRC `16d57521`,
before the existing writer restored physical mtd4. Candidate-prefix comparison
and full-slot CRC `d6b13baa` passed; mtd0/mtd1/mtd2/mtd3/mtd5 and bootenv were
preserved. The post-flash platform checks and final authenticated UART binding
passed. The production recovery-proof reader revalidated all five transcript
digests and platform checks at 15:40 UTC.

This is a controlled self-restore from an intact F314 slot, not a demonstration
of recovery after partial erase or a hard CPU lockup. The historical mtd3
rootfs failure remains unresolved; this result does not claim safety-slot boot.
No F319 installation or claim/map/unload occurred in this rehearsal.

At 15:40 UTC a fresh SSH attempt timed out. Windows still enumerated the pinned
FTDI on COM3 and no physical lock or matching hardware process was present,
but Ethernet had address `192.168.137.219/24`; traffic to HGW `192.168.1.90`
was routed through `192.168.137.1`. These are host observations, not proof that
HGW failed. No further UART open, reboot, flash or host network change was made.
Restore a verified management path to HGW, then acquire a fresh physical binding
before promoting the already-authorized exact F319. The completed rehearsal
can now satisfy the promoter's `-RecoveryRehearsalResultPath` prerequisite.

The same management-path blocker was recorded at 15:43 UTC in
`outputs/preflight/f319-management-path-20260907T154349Z/result.json`, without
opening UART or changing the host network. The objective audit now reuses the
production file-only recovery-proof reader instead of treating a PASS label as
sufficient evidence. Its focused 24-check regression passed at
`outputs/preflight/f319-recovery-audit-20260907T154305Z/tests.xml`.

### Management subnet restored, HGW still unreachable — 2026-09-07 17:48 UTC

The owner reported Internet restored. Read-only checks now show Ethernet on
static `192.168.1.249/24`, gateway `192.168.1.1`; the previous host-subnet issue
is resolved and DHCP renewal is not applicable. HGW `192.168.1.90` remains
`Unreachable` in the neighbor table and TCP 22/80/443 do not connect. The pinned
FTDI remains present, with no shared lock or matching hardware process, but
this does not identify the attached board. Current router runtime is unknown.
Evidence: `outputs/preflight/f319-management-path-20260907T174826Z/result.json`.
No UART open, reboot, flash or host-network change occurred. The next need is
HGW power/LAN connectivity and fresh pinned SSH, not another recovery rehearsal.

### First F319 physical attempt, host-verifier failure — 2026-09-07 18:15 UTC

After the owner powered HGW on, fresh pinned SSH confirmed F314, both radios
ready and zero fatal markers. The promoter acquired its fresh authenticated
UART binding and live guard. Exact F319 was installed; full-slot CRC `22d3802a`,
candidate-prefix comparison, protected partitions and the platform gate passed.
Flash evidence is under the private device firmware directory
`f319-device-bound/flash-one-shot-20260907T175648Z`; the platform result is
`outputs/postflash/f319-device-20260907T175632Z/status.json`.

The probe stdout at `outputs/preflight/f319-runtime-probe-20260907T181448Z/`
records claim/mapping Y, read/write counts zero, provider N, unchanged MTD table,
zero fatal counts and successful unload. However, final acceptance failed:
Windows PowerShell 5.1 returned a null process ExitCode after capture completion.
The capture reported complete with zero gaps, but an unknown exit code cannot
be accepted. No PASS result was manufactured for that attempt. The promoter
started its automatic exact-F314 rollback under the same held guard.
The immutable failure record is
`outputs/flash-watch/f319-promotion-detached-20260907T175630Z/acceptance-failure.json`.

The failure was reproduced locally with synthetic children, including exit 7.
Retaining the child process Handle immediately after Start-Process preserves
the real ExitCode in PowerShell 5.1; PowerShell 7 was also checked. Evidence:
`outputs/preflight/f319-capture-exitcode-20260907T182020Z/`.
The runtime gate now retains that handle and records capture PID/run ID/exit
code in successful results. Null and nonzero exits remain failures.
Six tests exercising the actual production lifecycle lines and local dry run
pass at `outputs/preflight/f319-capture-exitcode-fix-20260907T1824/tests.xml`;
78 guard/capture/transport checks pass with current source hashes at
`outputs/preflight/f319-offline-guards-20260907T182547Z/result.json`.
The earlier failed test report at `f319-capture-exitcode-fix-20260907T1823`
is preserved: its four failures were an over-strict empty-stderr assertion on
synthetic EncodedCommand children emitting PowerShell module-preparation
progress, not lost exit codes. The fixture now disables that progress stream.
Firmware and module binaries remain unchanged. A fresh complete physical gate
is still required after rollback; the first attempt is not retrospectively PASS.

The automatic rollback completed at 18:34 UTC: exact F314 prefix comparison,
full-slot CRC `d6b13baa`, protected partitions and the F314 platform gate passed.
Its writer result is in the private firmware directory
`f314-device-bound/flash-one-shot-20260907T181609Z/result.json`; platform proof is
`outputs/postflash/f314-restored-from-f319-20260907T181557Z/status.json`.
The promoter emitted `OMF319_AUTOMATIC_F314_RESTORE_PASS=1`, terminated and
released its guard. Fresh pinned SSH then confirmed F314, both radios ready,
zero fatal markers and no owner module loaded. The same authorized F319 image
was retried at 18:37 UTC with fresh binding and the corrected verifier:
`outputs/flash-watch/f319-promotion-detached-20260907T183724Z/launcher.json`.

The objective audit now distinguishes incomplete physical attempts from an
accepted runtime result. It rechecks exact firmware/module identity, actual
recorded capture exit code, PID/run correlation, raw/text equality, unique
capture brackets, zero-access/unload stdout and unchanged MTD/fatal counters.
Its focused 46-check regression passed at
`outputs/preflight/f319-runtime-audit-20260907T1841/tests.xml`.

### Second attempt: pre-flash YMODEM failure — 2026-09-07 18:51 UTC

The second transfer exhausted its retransmission limit. Its last reported
progress was 79% (4,180,992 bytes); this is not the exact final received size.
The loader raised `YMODEM sender reported failure`, and the generic runner
stopped with `UART/YMODEM candidate load failed` before invoking its flash
backend. No RAM validation status, flash-backend transcript or flash result was
produced. The unchanged runner orders successful loader completion before the
backend call, so this attempt performed no erase/write; the exact restored
F314 remains the expected persistent image. Current runtime is unknown.

The promoter terminated and released its guard. FTDI still enumerated, but
pinned SSH timed out; the captured tail contains ACKs, not a current Bootbase
prompt or evidence of a running kernel. No further UART transmission was made.
The owner needs to power-cycle HGW only (not factory RESET), then fresh pinned
SSH/UART binding can be reacquired. Do not reuse the ended guard as authority.
Evidence:
`outputs/flash-watch/f319-promotion-detached-20260907T183724Z/transfer-failure.json`;
private loader logs: `f319-device-bound/flash-one-shot-20260907T183743Z/`.

The existing TFTP helper was inspected but not started: its default listener
binds all interfaces and serves the shared `work/tftp/omvl` root. A network
retry needs a candidate-only root and target-scoped listener/client policy;
do not expose the private firmware collection as a shortcut.

### Scoped TFTP and accepted physical F319 — 2026-09-07 19:29 UTC

After the owner's HGW power-cycle, fresh pinned SSH confirmed exact F314,
both radios ready and zero fatal markers. The existing recovery proof was
revalidated without repeating its physical rehearsal. F319 authorization and
both immutable firmware/module hashes remained unchanged.

The one-shot writer now serves a hash/size-verified candidate copy from a new
attempt-only directory. The listener and transfer socket bind to the selected
local address; requests must match the exact target IP and candidate filename.
Writes, other files and path aliases are refused. A failed listener prevents
backend invocation. Cleanup removes only this attempt's copy and empty serving
directory, never the original artifact or evidence. The existing Windows
firewall already allowed this Python executable; no firewall rule was changed.

Offline evidence:

- 42 loopback/mock/transport checks:
  `outputs/preflight/f319-scoped-tftp-20260907T1920/tests.xml`.
- 78 Windows ownership/capture/argument checks, now also pinning the TFTP source:
  `outputs/preflight/f319-offline-guards-20260907T192300Z/result.json`.

Physical attempt:
`outputs/flash-watch/f319-promotion-detached-20260907T192431Z/launcher.json`.
Fresh authenticated HGW-to-UART binding and exclusive ownership preceded
SysRq. The live guard remained held through flash, platform and runtime gates.
TFTP from `192.168.1.249` served only the exact F319 to HGW `192.168.1.90`.
Bootbase received 5,292,032 bytes, accepted iminfo and RAM CRC `1d9fa16c`,
and checked current F314 slot CRC `d6b13baa` before erasing only mtd4.
The write, full-slot CRC `22d3802a`, exact 5,292,032-byte prefix comparison,
protected mtd0/mtd1/mtd2/mtd3/mtd5 and unchanged boot selector all passed.
Writer evidence:
`outputs/flash-watch/f319-direct-20260907T192433Z/tftp-attempt/result.json`.

Runtime acceptance at `2026-09-07T19:29:01.3602193Z`:
`outputs/preflight/f319-runtime-probe-20260907T192754Z/result.json`.
Claim and mapping succeeded; reads/writes remained zero; provider stayed
disabled; MTD table and zero fatal counts were unchanged; the module unloaded.
The correlated RX-only UART capture completed with zero gaps and actual exit
code 0. Its run ID is `f319-b146110193204b069c3c85fea2a679cc`.
The promoter emitted `OMF319_MTD4_PROMOTION_AND_OWNER_PROBE_PASS=1`, terminated
and released its lease. The TFTP listener stopped and temporary serving copy
was removed; original firmware artifacts and all logs remain intact.

Independent post-probe platform verification passed at 19:29:44 UTC:
`outputs/postflash/f319-postprobe-20260907T1929/status.json`.
Additional pinned SSH observed exact F319, boot ready, 2.4 GHz ENABLED, 5 GHz
ready, no owner module in sysfs and zero fatal markers. These are control-plane
checks, not new client association/traffic measurements. No cold power-cycle
was performed after installing F319.

The objective audit independently revalidates the complete runtime record and
reports `PHYSICAL_PASS_RECORDED`; F319 remains installed, with F314 preserved
as the exact recovery artifact. The prior successful automatic F314 rollback
and Bootbase rehearsal remain the recovery evidence. The historical mtd3
rootfs failure is not reclassified as a working rescue system.

This completes the F319 ownership milestone only. Do not automatically repeat
its flash/probe. A bounded SPI read or any write/provider, and F315/F316/F317
radio work, each remain a separate versioned gate with applicable authorization.
