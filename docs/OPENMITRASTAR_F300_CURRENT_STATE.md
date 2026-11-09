# OpenMitraStar F300 Full current state

Date: 2026-09-04

## Installed Image

F300 is installed persistently in physical `mtd4/linux_live`.

- Runtime: `lyoko-foundation-6.5.3-f300-emac-hw-demand-two-sample-device`
- Candidate bytes: `5259264`
- Candidate SHA-256: `734bba8ad1b706c0c17ad5e73341cbb7c7a5c4d78cf05e069d955705d789edbb`
- Full-slot CRC32: `841f11c8`
- Full-slot SHA-256: `fb7867874640a428124a18be38b8521e52e5d27322393f88ab44bbd6d17baf9b`
- Bootbase TFTP write/readback: PASS
- Protected partitions: PASS
- Linux 5.10, SquashFS, SSH, web/API and dual-radio readiness: PASS

## Realtek 2.4 GHz

Three physical 32 MiB bidirectional runs passed.

- Download: `19.857 / 27.990 / 27.929 Mbps`
- Median download: `27.929 Mbps`
- Upload: `14.688 / 15.275 / 14.861 Mbps`
- Median upload: `14.861 Mbps`
- F290 95 percent floors: `27.795 / 13.689 Mbps`
- Fatal markers, RX allocation failures and MAC counter read failures: zero

The demand-gated recovery branch fired during run 1 at poke 2 and 2510 ms,
with two consecutive MAC progress samples, a DMA-owned head descriptor and a
real `NO_RX_DESC` observation. The client remained associated and completed
both transfers.

Compared with the equivalent stalled observations:

- F290: poke 16, 6150 ms, 14.769 Mbps down.
- F299: poke 13, 5390 ms, 14.158 Mbps down.
- F300: poke 2, 2510 ms, 19.857 Mbps down.

The complete F290 16-poke fallback and ten-second cooldown remain present.

## Quantenna 5 GHz

The exact F300 image passed a real AELITA client gate:

- WPA2/CCMP association on channel 36.
- 802.11ac, negotiated 866.7 Mbps PHY.
- 32 MiB download at 30.588 Mbps.
- 32 MiB upload at 24.166 Mbps.
- 120-second soak with 111/111 connected samples.
- Zero disconnects and zero fatal markers.

## Campaign Reconciliation

The first complete campaign automatically restored F292 after all traffic gates
had passed because its final health step used a monolithic SSH command that
returned a false negative. The final-health harness now performs diagnostic
field reads with convergence retries.

The exact F300 hash was then installed again. Fresh full-slot readback,
protected-partition, platform and live-health checks passed, so F300 is the
current physical image. Traffic was not repeated after the harness-only fix;
the preserved physical evidence belongs to the exact same firmware hash.

## Evidence

- `outputs/campaign/f300-flash-test-20260904T101541Z/physical/f300-evaluation.json`
- `outputs/campaign/f300-flash-test-20260904T101541Z/physical/quantenna-sanity/result-20260904T103640Z.json`
- `outputs/campaign/f300-flash-test-20260904T101541Z/f300-promotion-reconciled-20260904T104515Z.json`
- `%USERPROFILE%/.openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f300-device-bound/flash-one-shot-20260904T104208Z/result.json`
- `outputs/postflash/f300-device-20260904T104158Z/status.json`
