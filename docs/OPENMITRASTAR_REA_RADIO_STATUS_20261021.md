# HGW radio work — 21 October 2026

Latest continuation: exact F365 5 GHz modules remain active in RAM on the same
R9 boot. A new 61-second read-only capture passed SSH, both radio control planes,
bridge preservation and bounded fatal-marker checks. No client was observed.
F370 is now a complete qualified module, and F371/F372 full images are prepared
offline. See `docs/OPENMITRASTAR_F370_COMPLETE_MODULE_20261021.md`,
`docs/OPENMITRASTAR_F371_NORMAL_START_COMPAT.md` and
`docs/OPENMITRASTAR_F372_AUC_TQE_OBSERVATION_IMAGE.md`.

Correction of the earlier utility interpretation: the live probe at
`outputs/rea/arc700-20261021-r2/runtime-utility-probe-20261021T194330Z` proves
`/bin/head -n` and `/bin/tail -n` work, including direct BusyBox invocation.
Only `head -c` is unsupported. The original claim that those line utilities were
missing was incorrect. F371 remains a coherent offline compatibility variant,
but its helpers are not demonstrated to repair a current line-utility failure.
F370 measurement remains valid and F372 includes it. `head -c 32` affects only
an inherited configuration-transaction ID path; it does not explain QDRV startup
or invalidate the line-based fatal diagnostics.

Current physical HGW-500BNA-QCv2 A2 observations belong to boot
`5f513265-a294-4366-9567-e1d8af704b6b`. Persistent image identity is
`lyoko-foundation-6.11.8-f367r9-transition-observation-device`, Linux
`5.10.260-openmitrastar-radiohw`, `#358 @1790006400`.

SSH at `192.168.1.90` is reachable through the PC's existing
`192.168.1.49/24` Ethernet interface18. The owner moved the cable from the
connector observed as `eth1` to the connector observed as `eth0`; reachability
returned immediately. Both are bridge members, but secondary-port management
was not working in the first observation. Do not describe this as a complete
causal diagnosis of that Ethernet defect. No PC IP/route was changed.
The original FTDI identity `AG41W2BL` now enumerates as COM4, not COM3.
The R9 rootfs has no interactive console configured in `/etc/inittab`.

## Current radio state

The 5 GHz AP is now running from an exact F365 module pair uploaded to RAM:

- qdrv: `cfb1b5c49eba15a0b114bb695d68dce07629d9600387a26d3c65d7ae573a4b01`.
- wlan: `f4f6099b43dd675dd44e7021374f1ea2f4380a4d9d9fd81b1d35ea411984897f`.
- Runtime package: `/run/openmitrastar/f365-ram-20261021-r3`.
- Package: `outputs/rea/arc700-20261021-r2/f365-ram-activation/r3/package.tar`.
- Package SHA256: `7fe2dc8082392d27c0d84f58e00de1dd432b56f296bc2dc0b17f426ea2b90393`.

F365 and R9 kernel/config/DT hashes match. Unchanged dependencies were verified
against the actual R9 rootfs. The normal F365 starter changes only PATH to add
package-local head/tail compatibility helpers; original starter is retained.
No native radar, DFS campaign, watchdog arm, firmware write, reboot or persistent
boot-environment change was performed. The original recovery quarantine remains
unchanged; the activation used an exclusive child F319 lease and SSH/UART nonce.

Physical control-plane PASS: hostapd PONG, RF1, wifi0 UP/carrier1, channel36,
mode `11ac80Edge+`, 21dBm reported. Domain getter21317 corresponds to the existing
ES representation; no regulatory or calibration settings were changed.
Ethernet/SSH and 2.4 GHz remained available; fatal count0 and watchdog00000000.
The configured RAM keep-running flag prevents the outer240-second stop after
control acceptance. Reboot loses this RAM package and returns to R9's diagnostic
default with 5 GHz disarmed. Persistent 5 GHz acceptance is NOT established.

2.4 GHz: wlan0 ENABLED, channel1/2412MHz, bridge member, zero fatal markers.
No current physical client was observed; historical F314 traffic evidence is
not a maximum-performance claim or a fresh F367r9 client gate.

Client/traffic/soak/cold boot/recovery/release acceptance remain separate.
AELITA192.168.1.63 did not answer TCP22. Owner mobile association was requested;
until observed, SSID visibility, AUTH/ASSOC/AUTHORIZED and useful bidirectional
client traffic are UNPROVEN in this run.

## REA and driver correction

Stock REA6.7.0 rejects ELF EM_ARC_COMPACT93. A project-local Linux copy adds a
bounded ARC700 ELF32LE recognition lane with Ghidra12.1.4 and the existing
ARCompact Sleigh source. Installed REA and Codex configuration were unchanged.
Results are local adaptations, not upstream-supported ARC proof. ET_REL calls
were unresolved until derived ANALYSIS_ONLY linked ELF files were produced with
the pinned ARC linker. Synthetic external addresses are not runtime addresses;
the derived ELFs must never be loaded, packaged or flashed. All original module
bytes remain unchanged. Pseudocode bad-data warnings are decoder limitations,
not evidence of physical kernel faults.

REA inspected the real R9 qdrv producer and the RTL PCI RX worker from the R9
rootfs. Initial RTL8192EE IRQ analysis was an older artifact and is not current
driver evidence. Exact outputs and manifests are under
`outputs/rea/arc700-20261021-r2`.

F368 normalized STORE38 completion and stopped channel transition on failure.
The expanded failure-chain test reproduced a late STORE38 completion falsely
confirming subsequent TX-off26 after descriptor reuse. F368 is NO_GO.

F368r2 retains only the published STORE38 descriptor on timeout. Its four-slot
replay passed16cases/80checks twice identically. OFF uses a different slot and
requires its own completion. This is an injected software reproduction, not
proof of physical MuC timing or RF silence. Other raw producers remain outside
this correction. qdrv builds match twice:703624bytes, SHA256
`01402519e44293b2311c395edf5ae9f56c77a076780669a3b9179fe9af25c240`.
393imports/15exports unchanged. No F368/F368r2 module has been loaded on the HGW.
F369 now packages F368r2 into a new5468160-byte full image, SHA256
`d803af79949e4d0bb26791c8f234976f66a2934d724c01ed4b4d0486f067250e`.
Two repacks, Bootbase and prefix fit pass. See
`docs/OPENMITRASTAR_F369_STORE38_CANDIDATE.md`. Installation and physical
acceptance remain pending; diagnostic activation is retained.

F355 pins qdrv after admitted mutation; the currently loaded F365 qdrv reports
retained1/reboot_required1/release_supported0. Hostlink stop is a no-op, AuC stop
empty and ARC DSP stop deliberately disabled due to bus hangs. Callbacks, work,
IRQ/DMA ownership must be retired before a future unpin can be safe. Repeated
module replacement after radio start is not supported. Owner accepts full-image
flashing between qualified iterations; hot reload is not required for progress.

## Evidence

- `outputs/rea/arc700-20261021-r2/physical-prepare-20261021T190629Z/result.json`.
- `outputs/rea/arc700-20261021-r2/physical-activate-20261021T190646Z/result.json`.
- `outputs/rea/arc700-20261021-r2/live-ssh/baseline.txt` and `quiescence.txt`.
- `outputs/rea/arc700-20261021-r2/live-ssh/radio5-running.txt` and `radio5-settings.txt`.
- `outputs/rea/arc700-20261021-r2/f368-fault-path/result.json` (NO_GO).
- `outputs/rea/arc700-20261021-r2/f368r2-fault-path-r2/result.json`.
- `outputs/rea/arc700-20261021-r2/f368r2-module/result.json`.
- `outputs/rea/arc700-20261021-r2/status-20261021T191300Z.json`.

Future OEM-to-5.10 update demonstration remains unimplemented. This HGW's OEM
kernel is2.6.35.12, not2.10. Preserve OEM and physical protected partitions;
derive and qualify the OEM upload/boot contract before any migration action.
