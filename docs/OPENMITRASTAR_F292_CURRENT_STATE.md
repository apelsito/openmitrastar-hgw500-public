# OpenMitraStar F292 Full current state

Date: 2026-09-04

## Installed image

- Runtime: `lyoko-foundation-6.5.0-f292-emac-diagnostics-ui-device`
- Physical target: `mtd4/linux_live`
- Candidate bytes: `5259264`
- Candidate SHA-256: `bb796f406c0e7941a868b329234611f014809d5cd2643565fad9888b3cd48b1e`
- Full-slot CRC32: `e40dada0`
- Full-slot SHA-256: `9c6dbb456207eb4006c791be76e8f40d58843e198f03abb9c0676d60202a94b1`
- Bootbase TFTP write/readback: PASS
- Protected partitions and store tail: PASS
- Platform gate: PASS

## Developer diagnostics UI

F292 is a rootfs-only update over the F290 kernel. The Developer diagnostics
page now presents twelve live metrics in a full-width workspace and provides an
interactive explanation panel for IRQ, NAPI, descriptor pressure, RX fault
observations, recovery counts, recovery timing and TQE counters.

The health indicator distinguishes:

- no new fault or recovery;
- RX pressure handled without restart;
- recovery associated with a recently observed RX fault;
- recovery without a recent visible cause;
- fatal kernel/firmware markers.

Desktop and 390x844 viewport checks passed with zero horizontal overflow. The
metric selector updates its explanation and state without navigating away from
the diagnostics page.

## Live verification

The physical router serves the exact packaged frontend hashes. The authenticated
diagnostics backend exposes the F290 restart-context fields, including fault
observations, last fault status/age and last restart status/age. Linux 5.10,
SquashFS, SSH, both radios, bridge membership and API protection remain intact.

Evidence:

- `%USERPROFILE%/.openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f292-device-bound/flash-one-shot-20260904T003353Z/result.json`
- `outputs/postflash/f292-device-20260904T003344Z/status.json`
- `docs/OPENMITRASTAR_F290_CURRENT_STATE.md`
