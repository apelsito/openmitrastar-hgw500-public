# F372 installation preparation - 21 October 2026

F372 has a concrete file-only installation contract and a separate read-only
postboot verifier. No F372 physical installer has been executed or accepted.
The HGW still runs installed F367r9 with the exact F365 5 GHz module pair in RAM.

## Contract and exact artifacts

Contract plan:
`outputs/preflight/f372-install-20261021T195348642022Z/plan.json`, SHA256
`a502abe660e7da3e3d561d3f8995ac0d43701cb683e3b03d919d5234e97c25c1`.
It binds 298 files and passes 21 offline fault checks. Its CLI has no execute
flag. Synthetic authorization tests are not owner authorization.

- F372 candidate: 5382144 bytes, SHA256
  `e8f7315c286e98d73f6bf4152c652f4633c8f63bd4a72b8a300e6859af619ef9`.
- F372 full-slot checksum model with preserved store: CRC32 `9a81d387`.
- Exact F365 return: 5382144 bytes, SHA256
  `43f4655f09eb01d749ca24c003689470b2f7c2d2738333297348e965e56d5355`,
  full-slot model CRC32 `118901d4`.
- Store: 1835008 bytes, SHA256
  `fcbeb5ab9f1fde273632a0f1a2f0a5d8b1304aa361439c24d1fe8e29cbb1c873`,
  CRC32 `5d2ee646`.

Only the physical live firmware prefix `0x7e0000+0x5e0000` is a future normal
write target. It ends at `0xdc0000`, before the store. The current Linux
`mtd3=rootfs_live` and `mtd4=lyoko_store` are logical views and must not be
interpreted as same-numbered physical partitions. Physical mtd0/1/2/3/5 and
logical mtd6 remain excluded. Full-slot checksum models are not flash files.

## Outstanding physical gates

Generic acceptance of flashing does not identify this new artifact. Execution
requires explicit authorization of its exact image, hash, size, destination,
reboot and conditional exact F365 return, plus a reviewed executor and fresh
device/transport/readback/recovery evidence. The plan remains physical NO_GO.

The old F365 executor cannot be run unchanged: it binds F364/F365, COM3 and a
different return path. R9-return also requires qdrv/wifi0 absent, while the
present normal F365 RAM radio is active and pinned. New adaptation must bind
COM4+FTDI AG41W2BL, PC Ethernet18/.49, HGW .90, exact boot and retained-parent
child ownership. The quarantine parent must remain unchanged. No redundant
firmware reference copy is required.

The proposed sequence is identity/ownership admission, continuously captured
authorized reboot, fresh Bootbase, physical protected/store/R9-slot readback,
exact scoped transfer, prefix-only erase/program, byte comparison and CRC,
new F372 boot and control validation. A conditional return requires a fresh
prompt, verified domain and no ambiguous write. An uncertain write cannot
authorize another write or reset automatically.

Recovery is not currently accepted: the preserved physical safety image has
a valid kernel contract, but its original recorded boot failed mounting rootfs.
`outputs/recovery/mtd3-current-evidence-20260901/result.json` SHA256
`1fc190e9e920b5afde938ae26be6bb6d450813b4b931e250f0c3eccbc1fa57e7`
reports `RECOVERY_NO_GO_ROOTFS_MOUNT_FAILURE` and no management/SSH recovery.
The instructions' named manual ATGO route is not a substitute for fresh
physical proof. Historical exact F314 Bootbase self-restoration proves its
own scope, not independent mtd3 recovery or hard-lock/partial-erase recovery.
Do not use a legacy helper that calls saveenv/qtnboot as a shortcut.

## Postboot verifier

`tools/f372_postboot_gate.py` is offline by default and accepts an explicitly
selected captured transcript. Its `--observe` mode only reads pinned SSH; it
does not start/stop radio, UART, reboot or flash. It verifies candidate identity,
a new boot, exact hashes of 92 runtime bindings, loaded qdrv srcversion, four
read-only uint counters, non-DFS36 RF/carrier/hostapd, 2.4 GHz, bridge, store,
configuration, watchdog and fatal-marker count. Client traffic, repeated cold
boot, physical protected readback, recovery and final release are excluded.

The synthetic fault suite `tools/test_f372_postboot_gate.py` passed 140 checks
at both its original revision and the revision rejecting unknown MTD flags.
These tests demonstrate verifier behavior, not physical F372 acceptance.
The read-only shell probe is emitted with LF bytes for Linux syntax. An earlier
CRLF template remains preserved as a failed host-format attempt.

## Current client window

Owner offered an iPhone 18 Pro. The actual 5 GHz SSID was read as
`MOVISTAR_PLUS_55CB`, channel36/80, RF1 and hostapdPONG. A read-only association
window is stored under
`outputs/rea/arc700-20261021-r2/iphone-association-window-20261021T195600Z`.
The completed window contains 50 samples over 301 seconds: SSH and both radio
control planes stayed available, the bridge and inactive watchdog were preserved,
and bounded fatal searches stayed at zero. No station or authorized client was
observed; Wi-Fi 5 GHz RX bytes remained zero. The owner's Wi-Fi-screen outcome
is still pending. This is inconclusive, not a proven association rejection.
Merely offering the phone, a healthy AP, packet counters or an unconfirmed
connection is not AUTH/ASSOC/AUTHORIZED or useful bidirectional traffic proof.
