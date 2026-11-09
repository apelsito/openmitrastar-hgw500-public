# OpenMitraStar F299 Physical Result

Date: 2026-09-04

## Classification

- Flash and readback: PASS
- Platform gate: PASS
- Realtek transport: PASS
- Early hardware-demand branch: PASS
- Safety gate: PASS
- Performance gate: FAIL
- Quantenna traffic gate: NOT RUN
- Release promotion: NO-GO
- Final installed image: F292

## Exact Candidate

- Bytes: `5259264`
- SHA-256: `92ddc564fc264e3e7e0e1fd1300e798af959bf6c4280f8972a0b8dba20c6221a`
- Full-slot CRC32: `0b419d91`
- Full-slot SHA-256: `9f8a96e00fb838851560809289abaf05986ec56018e9b5ba02c9c35a6bbc2b82`

F299 was written only to physical `mtd4/linux_live`. Full-slot readback and
the protected-partition gate passed.

## Physical 2.4 GHz Result

All three runs transferred 32 MiB in both directions and passed association,
WPA2 and router-health gates.

| Run | Down Mbps | Up Mbps | Early restart |
|---|---:|---:|---:|
| 1 | 26.628 | 14.690 | 0 |
| 2 | 14.158 | 14.763 | 1 |
| 3 | 27.709 | 13.789 | 0 |
| Median | 26.628 | 14.690 | - |

Against F290, median download was 8.99 percent lower and median upload was
1.94 percent higher. Download therefore failed the predefined 95 percent
acceptance floor of 27.795 Mbps.

## Proven Recovery Behavior

Run 2 exercised the new branch without losing the client, SSH or the AP:

- one `NO_RX_DESC` observation;
- Linux RX idle for 5390 ms;
- head descriptor DMA-owned (`0x80000000`);
- hardware MAC RX delta 3;
- four consecutive hardware-progress observations;
- early restart at poke 13;
- zero DMA missed frames;
- zero counter-read or RX-allocation failures.

F290 had restarted the comparable demand-bearing stall at 6150 ms and poke 16.
F299 therefore reacted 760 ms, or 12.36 percent, earlier. The branch is real
and safe in this observation, but the acceleration is too small to recover the
stalled transfer's throughput.

## Harness Correction

Two earlier F299 installations were rolled back before traffic because the
new campaign used a monolithic SSH readiness command. The platform and F299
runtime gates had passed; the failure was a transient test-harness preflight,
not a driver or boot failure. The harness now retries SSH and reports each
runtime field while waiting for convergence.

The third installation completed the three Realtek runs. The 5 GHz traffic gate
was not reached because the 2.4 GHz performance gate correctly failed first.

## Decision

The automatic rollback restored the exact F292 image. Readback, protected
partitions, Linux 5.10, SSH, web/API and both radio readiness gates passed.

F299 is retained as positive evidence that hardware-demand recovery works. The
next experiment must react closer to the first trustworthy MAC progress sample
while preserving the complete F290 16-poke fallback and cooldown.

## Evidence

- `outputs/campaign/f299-flash-test-20260904T093250Z/result.json`
- `outputs/campaign/f299-flash-test-20260904T093250Z/physical/f299-evaluation.json`
- `%USERPROFILE%/.openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f299-device-bound/flash-one-shot-20260904T093301Z/result.json`
- `%USERPROFILE%/.openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f292-device-bound/flash-one-shot-20260904T094905Z/result.json`
