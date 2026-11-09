# OpenMitraStar F256 configuration-store API candidate

F256 adds explicit `commit` and `rollback` operations for the F252 JFFS2 A/B
journal.

- Endpoint: `POST /api/v1/config/store`.
- Exact actions: `commit` or `rollback`.
- Requires session CSRF and `OPENMITRASTAR_CONFIG_STORE_V1` confirmation.
- The runtime backend still requires its disabled-by-default feature gate and a
  writable JFFS2 `/persist` mount.
- Only validated non-secret radio configuration may be stored.

Artifact:

- Bytes: `5242880`
- SHA-256: `2c9eba1b9fba5660668b3bc6a665261145c90d1e292e8f7659aa7bbf0f2ba0b8`
- Rootfs SHA-256: `6f7e66ff08fe0daaa4b7c7fabb95eaa1d9baa8f66111cc4f28e721ede29da180`
- Full-slot SHA-256: `adffc767b7f61a22748fafe7c661464f8da9e9a192a693e0d0e20e786e861cc2`
- Hardware status: `NOT_RUN`.
- Classification: offline hold, not authorized for flash.

Offline tests: 35 PASS. Browser commit and rollback flows PASS with no console
errors or horizontal overflow.
