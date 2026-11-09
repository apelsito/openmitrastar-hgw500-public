# OpenMitraStar F313 Physical Result

Date: `2026-09-05`

## Installation

F313 was written to physical `mtd4/linux_live` through the guarded Bootbase
path.

- Candidate SHA-256:
  `c8af9ef6e1ca5793bada0f1aa764eb08950f23629bc68315dd638dbfc4e10737`
- Full-slot CRC32: `56ea7ceb`
- Full-slot SHA-256:
  `8479b0107549f8a827c840cf8f6b37cfa30ed80933473be2208543ca20cd1aae`
- Candidate prefix comparison: PASS.
- Complete slot readback: PASS.
- Protected `mtd0`, `mtd1`, `mtd2`, `mtd3` and `mtd5`: unchanged.
- Linux 5.10, SSH, bridge and both radio ready gates initially passed.

## Product result

The authenticated live API reported:

- UI `6.8.1`, Developer-only console;
- `lyoko.radio.settings/v2`;
- 15 writable 5 GHz values including the already proven SSID;
- Quantenna DFS hardware present and Linux 5.10 provider absent;
- DFS policy fail-closed.

## Rejection condition

The first physical control-matrix attempt timed out during its first apply.
The subsequent live readback found `wifi0` on DFS channel `132` while the radar
provider remained unavailable. No control-matrix result was accepted.

A direct attempt to return `wifi0` to channel 36 did not complete and Ethernet
management became unavailable. A later controlled reboot did not restore SSH.
The FTDI adapter remains present as COM3, but a 30-second UART capture and a
240-second reset-line recovery attempt both received zero bytes.

No additional flash write occurred after installing F313. The exact cause of
the channel change is not yet proven. F313 must not be treated as an accepted
control-plane release until a physical power cycle restores visibility and the
channel behavior is reproduced under the new guard.

## Current physical state

- Installed slot: F313 in physical `mtd4/linux_live`.
- Ethernet/ping/SSH: unavailable at the last observation.
- UART device: present, zero received bytes.
- Next required external event: physical power cycle.

## Evidence

- `%USERPROFILE%/.openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f313-device-bound/flash-one-shot-20260904T234905Z/result.json`
- `outputs/postflash/f313-device-20260904T234855Z/`
- `outputs/uart-live/f313-post-reboot-diagnosis-20260905/`
- `outputs/uart-live/f313-reset-recovery-20260905.log`

