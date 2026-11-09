# OpenMitraStar F173 hardware inventory candidate

Date: `2026-09-01`

F173 is an offline Foundation branch from F171. It deliberately does not
include the experimental F172 NAPI change, so UI/API work remains separable
from datapath benchmarking.

## Hardware truth used

Live F170 exposes:

- three input devices: 2.4 GHz Wi-Fi, 5 GHz/WPS and reset;
- six LED class devices: both radio LEDs, RGB panel LEDs and stage0 alive;
- no `/proc/temp_sens`, thermal class device or Quantenna temperature command;
- no watchdog device or watchdog class registration.

F173 reports those facts as structured capability objects. Missing hardware
support is explicitly unavailable rather than represented by a fabricated
temperature or ambiguous string.

## Safety and scope

- Read-only API and frontend change only.
- No LED, GPIO, button, watchdog or radio mutation endpoint is added.
- Kernel, DTB, radio modules, bridge and configuration behavior are identical
  to F171/F170/F167.
- Physical validation: `NOT_RUN`.

## Built artifact

- Candidate:
  `work/mission-state/q3-persistent-composite-f173-lyoko-hardware-inventory-from-f171/build/openmitrastar-linux510-q3-persistent-f173-lyoko-hardware-inventory-from-f171-LZMA-OFFLINE-NO-FLASH.webformat.bin`
- Size: `4,964,352` bytes
- SHA-256: `615a9ab1801fc7aece854f3bb46484b8f6eb2f86d0f0a787f6efb58d43a9ec90`
- Candidate CRC32: `6c5f6678`
- Full-slot CRC32: `9b7bc83d`
- Full-slot SHA-256:
  `08c608d4bee0311d4f742c135ba5fa5e2f669821112aa6d9b3996e01af64745b`
- Bootbase and slot-fit: PASS
- Offline tests: `17 passed`
- Repeated build SHA-256: identical
- `SHA256SUMS`: PASS, 11 entries

Desktop and `390x844` mobile layouts were rendered in the Podman emulator.
Both show the complete hardware summary without horizontal overflow.

The exact F173 source is frozen under
`versions/lyoko-foundation-1.1-f173/`. Further package UI development uses
`versions/lyoko-foundation-1.2-dev/`.

## Offline build

```powershell
.\tools\build_f173_lyoko_hardware_inventory.ps1
```

The Foundation emulator is available locally while the validation container
is running at `http://127.0.0.1:18082/`.
