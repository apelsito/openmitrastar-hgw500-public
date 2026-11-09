# OpenMitraStar F237 Hardened Candidate

F237 supersedes F235 after an adversarial transaction and process-lifecycle
review.

## Hardening

- An applied change is provisional and arms an independent rollback watchdog.
- `POST /api/v1/config/commit` explicitly accepts the verified configuration.
- If commit never arrives, the previous snapshot is restored automatically.
- Expired applied state is rolled back rather than silently deleted.
- Quantenna verifies PID ownership through `/proc/PID/comm` and detects zombies.
- Partial Quantenna failures attempt an internal restoration before returning.
- `PONG` is insufficient: hostapd must report `state=ENABLED`.
- DFS channels are rejected during staging.
- Persistent commit claims remain disabled until a boot consumer exists.
- Contract reload failure disables all mutable UI controls.

## Artifact

- Bytes: `5218304`
- SHA-256: `46d7ab2fe356742854533834f69081b90701b95f1c163c86cb4afcbbb24607ed`
- Full-slot SHA-256: `69f0d9391b00eaa4199c3f201ec863e9659481f070f44a96e2c5fd9eb9cf244e`
- Rootfs SHA-256: `b0f4315560f870f64855bef631bf2cbc7c4825ec7d3c7167d7865c1931f39090`

F237 is eligible only for an explicitly authorized write to `mtd4/linux_live`.
Hardware validation remains `NOT_RUN`.
