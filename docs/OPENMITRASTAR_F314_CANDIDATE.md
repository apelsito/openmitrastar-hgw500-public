# OpenMitraStar F314 Candidate History

Date: `2026-09-05`

This document records the offline F314 candidate phase. F314 was subsequently
installed and physically accepted; the authoritative state is now
`docs/OPENMITRASTAR_F314_CURRENT_STATE.md`.

F314 began as the successor to installed F313. It adds a single safety rule:

> If the current 5 GHz channel requires DFS while the Linux 5.10 radar provider
> is unavailable, every Quantenna mutation endpoint fails closed.

The API/UI reports `qtn-current-dfs-without-radar` as `Protección DFS activa`.
The host control-matrix runner also refuses to begin unless the current channel
is one of `36`, `40`, `44` or `48`.

## Artifact

- Candidate bytes: `5,292,032`
- Candidate SHA-256:
  `a0c7350a50e5e4b532a0202982e6cd3c2d3da4e2e91079cd105473b248523f11`
- Full-slot CRC32: `d6b13baa`
- Full-slot SHA-256:
  `bc06db537f4eb20ae2b2c64c47262f44c678b1f46a035d2229a768aa36732989`
- Kernel SHA-256:
  `fefc38802811f6639b847cc8e4166b4b6ddd0b9c0361bfde3a31262b5d716649`
- Bootbase contract and slot fit: PASS.
- Hardware boot: PASS in the final installed candidate documented separately.

The kernel, modules, firmware, calibration, bridge topology and main UI remain
the exact F313 lineage. `om-qtnctl`, `om-radioctl` and `om-radio5-start` add the
runtime and final-boot non-DFS guards. The boot path explicitly selects channel
36 before hostapd and reasserts it after hostapd before the final guard. If the
final channel is nevertheless DFS without a ready radar provider, F314 performs
a redundant shutdown and requires readback of RF off, `wifi0` down, hostapd
stopped, `wifi0` detached from `br0`, and wired/2.4 management preserved.

## Validation

- F314 non-DFS guard tests: 5/5 PASS, including executable verified-stop PASS/FAIL probes.
- F313 inherited control/transaction tests executed against F314: 9/9 PASS.
- F314 host control-matrix tests: 3/3 PASS.
- F314 power-cycle watcher tests: 4/4 PASS.
- Combined focused suite: 26/26 PASS after adding the detached-watchdog and
  fixed-channel regression tests.
- Shell syntax: PASS.
- Reproducible two-build image: PASS.
- No router, UART, TFTP, reboot, MTD or flash action was performed while
  building F314.

The physical runner covers the 14 controls that remain available while DFS is
fail-closed. `tpc_interval` is explicitly blocked because qdrv removes its TPC
ioctls whenever DOTH is disabled. For
each control it stages one value, verifies the complete settings snapshot and
both radios while the value is active, rolls back, verifies the complete
baseline snapshot again, checks SSH and fatal markers, and records a resumable
checkpoint.  An ambiguous or timed-out apply always enters the emergency
rollback path.  Channel and bandwidth remain explicit rejection probes.

## Historical Promotion Boundary

After a physical power cycle:

1. verify UART from the first byte;
2. confirm whether F313 boots on channel 36;
3. promote F314 only through physical `mtd4/linux_live`;
4. prove that a DFS current-channel state disables all mutations;
5. run the resumable 14-control matrix only from a non-DFS channel and prove
   rejection of channel, bandwidth and TPC while DFS is unavailable;
6. run the physical 2.4 and 5 GHz traffic regressions before accepting F314.
