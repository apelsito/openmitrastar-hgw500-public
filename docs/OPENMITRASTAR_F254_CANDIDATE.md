# OpenMitraStar F254 configuration-store status candidate

F254 exposes the F252 A/B configuration journal through authenticated,
read-only `GET /api/v1/config/store` and the Advanced/System storage summary.

- Bytes: `5242880`
- SHA-256: `18c9f0c129266d39d5963fa25d614127acd48b9a0af6af7843673cde01ccff26`
- Rootfs SHA-256: `c674661916e5ebf60481077aaca9f0e890bac4922b942e8b91fbdf5d59973d7b`
- Full-slot SHA-256: `06ae020ed0a65ceaf7850b02bf26ba4b79befdd87992730f0a9932d55a72494f`
- Hardware state: `NOT_RUN`
- Classification: offline hold, not authorized for flash.

The endpoint reports mount readiness, feature-gate state, selected A/B slot and
integrity without mounting, formatting or writing `lyoko_store`.
