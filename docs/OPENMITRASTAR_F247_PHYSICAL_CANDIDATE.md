# OpenMitraStar F247 physical test candidate

F247 is the physical-test promotion envelope for the exact F246 firmware
bytes. It introduces no kernel or rootfs change.

## Identity

- Bytes: `5238784`
- SHA-256: `8bd786744ca618a012f585a4e2f5de50ea7850ea91d7d04c076fd9a753cbda12`
- Full-slot CRC32: `71280f5a`
- Full-slot SHA-256: `ca5a30d69b95425fb834910e964745273e88ba4f5ce33c48b0c72964ed9abeac`
- Runtime identity: `lyoko-foundation-4.9-f245-device`
- Normal write target: physical `mtd4/linux_live` only.

F247 is `candidate_eligible=true` and `flash_supported=true` for an explicitly
authorized hardware campaign. It is not release eligible and has not been
flashed.

## One-command campaign

Dry-run:

```powershell
.\tools\run_f247_flash_test_cycle.ps1
```

The execution path requires the exact acknowledgement embedded in the script.
It performs all preflight checks before invoking the flash promoter.

Sequence:

```text
preflight
flash mtd4
platform/SSH gate
signed package catalog and volatile lifecycle
2.4/5 GHz transactional control and rollback
three 32 MiB bidirectional 2.4 GHz runs
32 MiB bidirectional plus 120 s 5 GHz continuity
final fatal-marker and control-plane gate
```

The current dry-run blocks execution only because AELITA SSH is unavailable.
Router SSH, COM3 and the local traffic server at `192.168.1.43:8008` are ready.
An active `192.168.1.0/24` neighbor refresh found neither of AELITA's known
Wi-Fi/Ethernet MAC addresses; this is a client-presence failure, not an SSH-key
or router failure. Evidence is stored under
`outputs/preflight/aelita-discovery-20260902/`.

A public-key-only repair bundle is available at
`outputs/aelita-testbench/lyoko-aelita-testbench-recovery-20260902.zip`.
Its SHA-256 is
`536ecdb3245d57b852d5cfbe7debaf12f09e1ab0ce659556649c6a6498393bdc`.

## Rollback

`tools/restore_f222_mtd4_from_f247.ps1` restores the hardware-proven F222 image
to `mtd4` through UART/YMODEM after a complete verified F247 installation. It
requires its own acknowledgement and validates the expected F247 full-slot
identity before writing.

Interrupted-write recovery remains a manual Bootbase operation. `mtd3` is
preserved but is not claimed as an automatic recovery path because its rootfs
mount remains unproven.
