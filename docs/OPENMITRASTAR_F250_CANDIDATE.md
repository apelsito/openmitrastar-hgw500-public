# OpenMitraStar F250 LED control candidate

F250 adds a guarded, temporary front-panel identification operation without
changing the kernel, radio drivers, DMA, MTD layout or storage policy.

## Contract

- `POST /api/v1/hardware-led-test`
- CSRF token required.
- Confirmation: `OPENMITRASTAR_LED_IDENTIFY_V1`.
- Duration restricted to 1, 2 or 3 seconds per step.
- Runtime feature gate defaults to disabled.
- `om-ledctl` snapshots all controlled channels and restores them through an
  EXIT/HUP/INT/TERM trap.
- The API compares the complete before/after snapshot before returning PASS.
- No radio, bootloader, MTD or persistent configuration writes.

## Artifact

- Bytes: `5242880`
- SHA-256: `df99f6cb40d62da2fa8180d87f2c1898cfdfb7cff42b79ea0f2124de72d8c9b2`
- Rootfs SHA-256: `81ad18744ce9e933b91791f3b76d1cd3f05bca656df0e10737caf2fea89914da`
- Full-slot SHA-256: `38f4fa8ec45ff33eceddb56b8b2854a3c08df2b6501d5582dade91708501e89f`
- Hardware state: `NOT_RUN`
- Classification: offline hold, not authorized for flash.

Offline verification: 34 tests PASS. Browser execution confirms the Developer
control, success response, restored state message, no console errors and no
horizontal overflow.
