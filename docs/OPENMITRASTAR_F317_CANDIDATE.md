# OpenMitraStar F317 autonomous radio observer candidate

Date: 2026-09-05

F317 is the offline successor that adds the portable `lyoko-radiod` observation
and policy layer over the F316 image. It does not automatically apply radio
changes and is intentionally not flashable until F316 has passed its physical
DFS campaign.

## Artifact

- Candidate bytes: `5,361,664`
- Candidate SHA-256:
  `849e0ef6835cd4ad1ec78e9c0cf18fc94ca83970fdd3f8c6cd844a4220f6c84b`
- Full-slot CRC32: `62ed8671`
- Full-slot SHA-256:
  `936bb691fa3a112dd9e6cecea5ef7d9f3641492894876c96bbad4bead8b7cdee`
- Kernel SHA-256:
  `fefc38802811f6639b847cc8e4166b4b6ddd0b9c0361bfde3a31262b5d716649`

## Integrated behavior

- Portable C11 policy engine with integer-only scoring.
- Independent 2.4/5 GHz metrics, 15 percent hysteresis and 1,800-second
  stability requirement.
- Observe-only supervisor and authenticated optimization-status API.
- HGW-500BNA-QCv2 snapshot adapter with secret/MAC redaction.
- Strict multi-router board-profile schema packaged with the candidate.
- A/B journal and filesystem backend, currently under volatile `/run` only.
- Automatic apply and persistent flash writes disabled.

Current tests cover the engine, adapter, file backend, firmware contents and
board profile. Physical status is `NOT_RUN`; F317 must not precede F316's
hardware proof.

