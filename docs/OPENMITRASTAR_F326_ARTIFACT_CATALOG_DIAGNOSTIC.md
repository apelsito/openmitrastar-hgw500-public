# F326 catalogue-corrected single-boot diagnostic

Checkpoint: 2026-09-19 12:16 UTC. Target: HGW-500BNA-QCv2 A2, 192.168.1.90.

F326 is the F325 one-boot acquisition experiment with a corrected installed
artifact catalogue and version identity. It is not DFS/CAC acceptance or an
in-place hardware restoration implementation. The F325 lifecycle and hardware
limitations in [the diagnostic design](OPENMITRASTAR_F325_SINGLE_BOOT_DIAGNOSTIC.md)
continue to apply.

## Why this revision exists

F325 was written and verified in
`outputs/flash-watch/f325-ethernet-20260919T112602Z-bd1b0cae` but failed the platform
gate because the catalogue retained old hashes for `om-radio5-start`,
`om-radio5-stop` and `driver-contract.env`. The parent restored exact F321
automatically. The original attempt remains `FAIL_F325_EXACT_F321_RESTORED`;
its `automatic-exact-f321-rollback/result.json` is `PASS_EXACT_F321_RESTORED`.
No capture was reached. No old evidence is rewritten as a pass.

## Immutable artifact

- Private directory: `/workspace/user-home/.openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f326-f321-radar-once-device-bound`.
- Filename: `openmitrastar-linux510-f326-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH.webformat.bin`.
- Bytes: 5,320,704.
- SHA-256: `7500036d0c7215a74d509b39419f65463efbd575b18d15703b3d05312262a767`.
- Expected RAM CRC32: `868236f7`; expected full-slot CRC32: `53bea2a4`.
- Locally calculated full-slot SHA-256: `9177dbc363ef2ed078be112df36fd21161f394335ea333606094b81ab85d6178`. This is not a hardware measurement.
- Product: `lyoko-foundation-6.9.4-f326-radar-once-f321-device`, build `a89abc29b35959d9`.
- Manifest SHA-256: `1e7ce6b7bf293cb66c07cba91e8ef417e169d7c58476e29caef01d84a09aeb56`.
- Inventory SHA-256: `da13b9849db2c1a4b98f52624409d50f23b0f919c3a8b51fedfbbe6ecf0dcb0a`.
- Reproducibility: `outputs/preflight/f326-shadow-repro-20260919T114624Z/result.json`; byte-equal independent build, full metadata inventory, Bootbase PASS and slot-fit PASS.
- All 39 catalogue entries verified before packing and after unpacking.

The kernel, DTB, radio modules and capture semantics are unchanged. F325
protocol names in host filenames, recovery ACKs and `OM_F325_CAPTURE_ACK` are
intentional. Candidate promotion uses `OPENMITRASTAR_F326_MTD4_7500036D`.
Only physical mtd4 is an allowed firmware write target. Protected partitions,
OEM firmware, calibration and the storage tail remain outside the write scope.

## Offline execution qualification

Evidence directory: `outputs/preflight/f326-executor-20260919T114805Z/`.

- UART: 205 effective PASS. `uart-qualification.xml` preserves 204 PASS and
  the old ACK-expectation failure; `uart-ack-rerun.xml` proves the corrected
  exact-ACK test. `uart-qualification-provenance.json` maps every effective
  result to its original source. No runtime gate was relaxed.
- Ethernet/capture: 639/639 PASS in `ethernet-qualification-final.xml`.
  The earlier 638 PASS / 1 FAIL report is preserved. Its synthetic authorization
  fixture was updated from the old F325 digest to the exact F326 digest.
- Final review: `ethernet-executor-review.json`, SHA-256
  `9c14f41d4842f88989a4e4ad117e39ff713415ec7ff14df4d98502ae52ad1cdd`.
- 83 execution sources frozen and hash-checked in `final-source-snapshot/`.
- `final-plan.json`: `OFFLINE_READY_FRESH_PHYSICAL_GATES_PENDING`, SHA-256
  `19c0f7b86e80d42d142af421c7f1a4d546ebf73ba7fdb3c61496059ee166d736`.
- `readiness.json` records these bindings, launcher checks and fresh F321
  observations. Firmware manifests remain sealed with their offline flags.

## One-click campaign and current state

Desktop command: `/workspace/user-home/Desktop/HGW F326 - prueba y retorno F321.cmd`.
It invokes `outputs/launchers/f326-oneclick-20260919T1214Z/launch.ps1` and asks
for legitimate Windows elevation. It changes no execution policy and creates
no persistent elevated broker. Without `-Execute`, the script only verifies
the file-only plan. One elevated campaign consumes its one-use claim so a
second click cannot silently repeat a failed flash.

The reviewed parent rechecks live topology, exact pinned SSH/UART identity,
exclusive ownership, current/protected readbacks and RAM integrity before any
write. Only a verified F326 installation and pristine postboot gate can reach
one capture window. The host must observe the autonomous software deadline
before any cleanup stop, then return once to exact F321. Inconclusive capture
does not waive restoration. Ambiguous writes or containment stop the chain.

No UAC, UART, flash or capture has been started by this offline preparation.
Pinned read-only SSH at 12:10:28 UTC confirms F321; the fresh platform check
passes 27/27 in `outputs/handoff-live/f326-resume-readonly-20260919T121028Z/`.
The owner must initiate the prepared desktop command. New evidence appears in
the launcher directory and `outputs/flash-watch/f325-ethernet-<UTC>-<id>/`;
the F325 directory prefix is the unchanged executor family name.

Physical hard-halt recovery can still need the owner's power-cycle. A stopped
worker does not prove capture hardware quiescence. Nonempty samples only prove
acquisition activity, not radar classification, DFS authorization, CAC or RF
conformance. No DFS transmit authority is granted by this campaign.
