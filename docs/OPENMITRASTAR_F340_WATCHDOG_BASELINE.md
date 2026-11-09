# F340: F321 baseline with an inactive watchdog and bounded supervisor

Prepared 21 September 2026, offline only. No device access, module loading,
watchdog arming, flash, radio or Wi-Fi/client/AELITA test was performed.
F338 DFS, F335 WPS and F339 sensor changes are not included.

## Artifact and qualification

Full firmware directory:
`/workspace/user-home\.openmitrastar\devices\hgw500bna-qcv2-a2-primary\firmware\f340-f321-watchdog-baseline-device-bound`.

- Image `openmitrastar-linux510-f340-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH.webformat.bin`:
  **5,349,376 bytes**, SHA-256
  `211c503a237107669ba8268529cd50b098022aac30c65c2683a5f7c8b823e2fa`.
- Manifest SHA-256:
  `91804168356f540401efb25abaa71e38f81f2de5c356b764d8b0b3f851369bed`.
- Reference full-slot CRC32 `2aa26ca6`, SHA-256
  `b7b7e703be684d7d664f77481ab139697c7d30dfa671d93b9bcf851fab05ecf7`.
- Product version `lyoko-foundation-6.9.6-f340-watchdog-baseline-device`,
  firmware build ID `da031c8a853ed18d`.
- Two independent kernel builds and two rootfs repacks/compositions produced
  identical images. Bootbase, slot fit and the boundary before store pass.
- `outputs/preflight/f340-qualified-20260921T134752Z/result.json`: **24/24**
  local identity, artifact, unchanged-runtime and no-autoarm checks pass.

The complete build report is device-local
`analysis/f340-fullimage-20260921T134349Z/result.json`. Only this full image is
the future mtd4 candidate; the intermediate kernel-only RAS is not a flash image.
No flash executor or physical acceptance is granted by an offline PASS.

## Preserved baseline and kernel identity

F340 retains all F321 init scripts, radio modules, radio bootstrap/control/API,
driver contract, radio artifact catalogue, calibration, device credentials and
UI bytes. Rootfs changes are exactly four files: the release record, the new
supervisor binary, its read-only profile and its artifact catalogue. There is
no new init service and no automatic supervisor startup or ARM command.

The kernel reuses the isolated F336 implementation, including F329 watchdog
ownership separation, without modifying those source snapshots. It has a new
`#340` UTS build identity and
`/proc/device-tree/openmitrastar,f340-watchdog-baseline = F340_WATCHDOG_BASELINE`.
The old F336 RAM marker is absent. Read-only owner attributes are now
`f340_control`, `f340_counter`, `f340_probe_seen` and `f340_probe_control`.

The configuration is byte-identical to F336, including nowayout, disabled boot
adoption and disabled old canaries. Probe registers an initially inactive
watchdog without control writes; a prearmed device is rejected. No stop or
safe-close primitive is invented.

Kernel build/report:
`/workspace/user-home\.openmitrastar\devices\hgw500bna-qcv2-a2-primary\analysis\f340-watchdog-kernel-20260921T132951Z`.
Its `a/` directory contains ELF, config, DTB and `Module.symvers`;
`a/build-directory.txt` identifies the exact KOUT. Source is
`/home/user/openmitrastar-build/f340-watchdog-20260921T132951Z/linux`.
The parsed qualification result is authoritative for the F340 node names;
the preserved kernel-stage report also records descriptive F336 reference names.

All five flash views remain `mtd-rom`. Rootfs stays at
`0x90960000+0x460000`; store stays at `0x90dc0000+0x1c0000`, unmounted and
read-only. Kernel entry is `0x8493e000`, load `0x8493a000`, end `0x84d02000`.
The image, CRC scratch and decompression ranges do not overlap.

## Supervisor and client protocol

`/usr/sbin/om-watchdog-supervisor` is a static ARC binary, 33,720 bytes,
SHA-256 `cc6492dc5d5689f30e3c22bdfd843e3bb40c2b19a53ddd6bdd94d3775d05fb9a`.
The default invocation or `--inspect` never opens a watchdog descriptor.
It reuses F336's identity, nowayout, inactive-control and standard ioctl code.
The old software rollback watchdog was not reused as a hardware supervisor.

Future explicitly qualified orchestration uses:

```
om-watchdog-supervisor --session TOKEN32 180000
om-watchdog-supervisor --status TOKEN32
om-watchdog-supervisor --request TOKEN32 1 ARM
om-watchdog-supervisor --request TOKEN32 1 BEGIN module-load 30000
om-watchdog-supervisor --request TOKEN32 1 COMPLETE module-load
om-watchdog-supervisor --request TOKEN32 2 BEGIN qdrv-core-start 30000
om-watchdog-supervisor --request TOKEN32 2 HEALTH ok
om-watchdog-supervisor --request TOKEN32 2 CEASE
```

`TOKEN32` must be a new 32-character lowercase hexadecimal nonce. Commands above
describe the API; they were not executed on the router. Starting a session does
not ARM. The unarmed session expires after 30 seconds without activation.

The sole watchdog descriptor belongs to the supervisor process. Its canonical
client only opens a private Unix socket at
`/run/openmitrastar/watchdog/supervisor.sock`, never a second watchdog descriptor.
The client checks socket ownership/mode, `SO_PEERCRED`, live PID start ticks,
boot ID, nonce and the response's command/request sequence. A stale JSON file
or a recycled PID is insufficient. `state.json` is an atomic observability
snapshot, not a substitute for the authenticated local response.

ARM request sequence is 1; its phase sequence remains 0. First BEGIN uses phase
1. Each BEGIN must increment the phase sequence and is accepted only while
waiting between phases. COMPLETE and HEALTH match the current phase. COMPLETE
leaves a five-second transition window. Repeated BEGIN or stale protocol input
cannot extend a phase. HEALTH `ok` does not extend any deadline; HEALTH `fail`
latches cessation. CEASE is an explicit global stop request, never a disarm.

The session has an absolute maximum of 180 seconds, starting at ARM. Each phase
is 100..60,000 ms, capped by the remaining total interval. Local pets occur
every second only while both deadlines and health remain valid. A blocked
bring-up process does not produce a new phase and therefore loses feeding at
the absolute deadline. On CEASE, expiry, health failure or SIGTERM after ARM,
the supervisor retains the descriptor and never resumes pets. It waits for
reset; it does not claim that closing, unloading or clearing EN can disarm it.

ARM exits successfully at the client only after matching identity, an open
descriptor, confirmed CR enable, successful first pet and an unexpired window.
Useful verified response fields are `nonce`, `boot_id`, `owner_pid`,
`owner_start_ticks`, `ack_sequence`, `phase_sequence`, `phase`, `fd_held`,
`hardware_arm_confirmed`, `first_pet_confirmed`, `pet_count`,
`timeout_reported_seconds`, `last_pet_monotonic_ms`,
`phase_deadline_monotonic_ms` and `session_deadline_monotonic_ms`.
The eight-second timeout is the driver's report, not a measured oscillator rate.

## Validation and remaining physical gates

`outputs/kernel-port/f340-supervisor-20260921T133917Z/result.json` records
20 tests of the actual deadline policy, nine real supervisor/client process
cases using the explicitly compiled fake-watchdog backend, GCC static analysis
and two identical static ARC builds. Tests cover no-open inspection, single
ownership, authenticated ACKs, invalid nonce, stuck-phase expiry, health loss,
duplicate phase rejection, FD retention and rejection of the wrong kernel or
already armed hardware. The production binary contains no test-backend switch.

F340 is unarmed and remains **NO GO for installation/arming until the separate
current-device campaign is qualified**. Root's F336 physical result must first
establish the relevant watchdog behavior. A stopped-petting process with its
FD held is not evidence of CPU/IRQ/bus-halt recovery or behavior after SIGKILL
and kernel handling of an unexpected descriptor close. No such claim is made.

The exact rollback is F321 image SHA-256
`eb8e23ac75ec50e113cd337e9b68ab86e366a09c8dbbec255a3b426843a9da18`,
5,337,088 bytes, through its guarded mtd4 path with fresh backup/protected-slot
checks. OEM safety is preserved; independently bootable mtd3 recovery is not
assumed. Wi-Fi/client/AELITA and RF testing remain deferred by the owner.
