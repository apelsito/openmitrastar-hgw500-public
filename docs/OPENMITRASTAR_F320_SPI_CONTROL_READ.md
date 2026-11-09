# F320: legacy-map-guarded SPI control snapshot

Date: 2026-09-07. Status: **OFFLINE PASS; physical campaign not yet run**.
The original artifact preparation performed no device operations. During executor
qualification, fresh read-only SSH confirmed F319, boot ready, both radio control
planes ready, fatal count zero and no loaded SPI probe. No F320 physical result
is inferred from that baseline. F319 remains the last accepted installed image.

## Why F319 is not a bus-access proof

The F319 result remains valid for exactly what it measured: a Linux resource
reservation and an ioremap return at `0xe4030000`, with no access to that bus.
It does not prove that this is the active SPI address, electrical arbitration,
or a transaction that can safely run alongside memory-mapped rootfs reads.

New source evidence identifies a concrete address discrepancy:

- `work/sources/Quantenna-GPL/common/topaz_config.h` sets
  `TOPAZ_MMAP_UNIFIED=0` and `TOPAZ_MMAP_ALIAS=0` and selects the first argument
  of `TOPAZ_ALIAS_MAP_SWITCH(a,b)`.
- `common/ruby_platform.h` consequently selects SPI `0xe2000000`, not the
  alias `0xe4030000`. `SPI_CONTROL` is offset `4`. Flash-command apertures such
  as ID/status are different addresses, not passive control-register reads.
- The exact F319 DTB corroborates the legacy peripheral layout: sysctl
  `0xe0000000`, UART `0xf0000000`, Ethernet `0xe8000000`. The independently
  decompiled DTB is preserved with the F320 module evidence.
- The actual Linux 5.10 `arch/arc/mm/ioremap.c` returns the input address for
  the ARC hardware-uncached range without testing the peripheral. A successful
  ioremap is therefore not evidence that an alias address decodes.

The F310 UART fault has ECR `0x00200400`, classified by the OEM ARC header as
`KERNEL_DATA_MEM_ERR`. Its ERET is `0x713d6060`; r0/r14 are `0xe4030000`,
r1 is `0x9f00`. The old module disassembly places a control load at init+0x50
and a call toward the ID read at init+0x60. Without recorded loaded-section
bases and precise bus-fault timing, do not claim which single instruction
caused the exception. The legacy/alias mismatch is an evidence-backed
hypothesis, not a physically confirmed root cause. The earlier claim that
missing ownership alone caused the fault was too strong.

## Exact bounded experiment

F320 changes only the diagnostic feature, not the existing kernel/radios:

1. Default module load refuses access unless `execute_read=1` is explicit.
2. Check exact HGW compatibility and reserve the legacy SPI resource.
3. Read the shared system-controller map register at `0xe0000004` once.
   Refuse the SPI access unless bits 29 and 30 are both clear. Never change them.
4. Map legacy SPI and read `SPI_CONTROL` at `0xe2000004` exactly once.
5. Report the raw control value, with map-read count 1, SPI-read count 1,
   write count 0 and provider unavailable. Unload releases resources without
   another register access.

There is no ID/status/DPB command, clock change, reset, write-enable, program,
erase, protection mutation, MTD registration, polling, retry or autoload.
The two dedicated ARC helpers each contain one 32-bit load and a return.
This bounds instruction count, **not bus completion time**. A read-only access
can still cause a fatal bus error.

## Immutable artifacts and offline proof

- Module: `outputs/kernel-port/f320-spi-control-probe-20260907T195338Z/`
  - `qtn-topaz-spi-control-probe.ko`: 7,592 bytes.
  - SHA-256: `6ec075b4875890d5f366ff568932b591b59cc15231282274d77bb868a768a06a`.
  - Nine actual-source host cases and GCC analyzer PASS.
  - Two independent ARC builds are identical; required symbols are exported
    by the exact F319 vmlinux, not merely an old build tree.
  - The prepared kernel config matches F319 SHA-256
    `cf01ec531be114cd77412712f2fdb54057ac65ddf3d30e8f4bfabe0f0c1aad9e`.
  - Missing Module.symvers warnings are preserved; export validation is done
    independently. No modversion coverage is claimed.
- Private firmware folder:
  `/workspace/user-home/.openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f320-device-bound`.
  - Image: `openmitrastar-linux510-f320-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH.webformat.bin`.
  - Bytes: 5,292,032.
  - SHA-256: `66ff3e8f11a054595ab349e9863789f6422e2ea2253f1a8da01840a6eb43a1fa`.
  - Full-slot CRC32: `f7e832d9`.
  - Kernel, DTB and radio contents remain byte-identical to F319.
  - Exactly three rootfs paths change: release, feature file and new module.
    Existing credentials and all other file contents/modes remain unchanged.
  - New module mode is `0777` as emitted by the existing NTFS-overlay builder;
    the SquashFS root remains read-only. This is recorded, not claimed as a
    permissions-hardening improvement.
- Independent firmware rebuild:
  `outputs/preflight/f320-firmware-repro-20260907T200250Z/result.json`.
- 23 source, binary-contract and real-image/Bootbase checks:
  `outputs/preflight/f320-offline-gate-tests-20260907/tests.xml`.
- File-only gate:
  `outputs/preflight/f320-spi-read-gate-20260907T200416Z/plan.json`.

The initial module build under `f320-spi-control-probe-20260907T1950` is
preserved as a rejected qualification attempt: GCC merged identical noinline
helpers, so the two-symbol disassembly requirement failed. The accepted source
uses `no_icf`; no failed result was relabelled as PASS or overwritten.

## Physical NO-GO and recovery

The actual kernel's `do_machine_check_fault()` calls `die()`, which executes
`flag 1`. A host timeout, SSH catch, exception-table fixup or SysRq command
cannot be assumed to recover a halted CPU. Physical HGW-only power cycling
must be available; this is not factory RESET and must not affect Askey.

The F314 Bootbase self-restoration and successful automatic rollback remain
valid historical evidence. They do not prove recovery from this hard-halt case
or repair the nonbooting mtd3 rootfs.

The immutable build manifest deliberately retains `candidate_eligible=false`,
`flash_supported=false` and `release_eligible=false`: these record the original
offline artifact, not subsequent permission or physical acceptance. The original
file-only plan is not an execution permit. Subsequent campaign qualification,
user authority and physical evidence are separate records, never edits to the
immutable image manifest. Required gates before hardware are:

1. Qualify an F320-specific promotion, runtime and rollback executor against
   the new hashes and failure paths, without loosening the F319 guard.
2. Obtain the exact new-image authorization and confirm physical power-cycle
   availability. Proposed acknowledgement: `OPENMITRASTAR_F320_MTD4_66FF3E8F`.
3. Acquire fresh pinned SSH/UART identity and the exclusive live lease; preserve
   protected-partition/readback gates and complete correlated UART capture.
4. Pass the read/unload/platform/dual-radio checks, or recover the exact F314.

Do not pass this image to a F319 runner or reuse its old acknowledgement. No
F320 physical success, SPI transaction provider or persistent store is claimed.

## Dedicated executor (2026-09-07)

`tools/promote_f320_mtd4.ps1` is the dedicated entrypoint, with a file-only default.
Its `tools/f320_campaign.ps1` implementation does not alter the F319 runners or
guard. `tools/qualify_f320_campaign.py` records source and artifact hashes plus
actual PowerShell 5.1/7 behavioral tests and exact-image shared-writer dry runs.
Any source/input drift invalidates qualification before device access.

Execution requires the exact F320 acknowledgement, explicit local TFTP address,
verified F314 restoration evidence, source-bound qualification and confirmation
that HGW-only physical power cycling is available. The user's "gogogog"/"goo"
continues this exact F320 campaign; the explicit power-contingency reply was "si".

Initial pinned F319 SSH precedes any UART open. The exclusive live guard and
authenticated console nonce precede reboot and the TFTP-only mtd4 writer.
Completed prefix comparison/full-slot CRC and protected-partition checks must
pass before the one-shot runtime probe. Fresh F320 binding and an already-ready
RX-only capture precede the single `execute_read=1` command. A timeout retains
the fixed capture window; unknown capture exit codes and missing/duplicate
markers cannot pass. SSH and UART register values must agree, with exactly one
map read, one SPI control read, zero writes, no provider and clean unload.

After a completed write, a responsive, pinned F320 can be restored automatically
to exact F314 under the original still-live guard. A fatal UART marker or a
nonresponsive system requires manual recovery; an ambiguous write is never
retried or switched to another transport. Restore-only mode accepts a fresh
F320 identity and restores F314 without loading the probe again. It does not
resume a failed flash or bypass current-slot CRC checks. Hardware acceptance
and release acceptance remain distinct.
