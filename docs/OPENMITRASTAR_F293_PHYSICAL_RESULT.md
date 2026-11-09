# OpenMitraStar F293 Physical Result

Date: 2026-09-04

## Classification

- Diagnostic objective: PASS
- Transport gate: PASS
- Telemetry gate: PASS
- Performance gate: FAIL
- Release promotion: NO-GO
- Final installed image: F292
- Overall result: PARTIAL, successfully rolled back

## Physical execution

F293 was written only to physical `mtd4/linux_live`. Boot, SSH, Linux 5.10,
full-slot readback and protected-partition checks passed.

Three physical Realtek runs completed 32 MiB downstream and upstream. No RX
allocation failures were observed and every run passed the router health gate.

| Run | Down Mbps | Up Mbps | New restart |
|---|---:|---:|---:|
| 1 | 27.204 | 14.114 | 0 |
| 2 | 13.983 | 14.279 | 1 |
| 3 | 26.133 | 14.459 | 0 |
| Median | 26.133 | 14.279 | - |

The F290 baseline is 29.258 Mbps down and 14.410 Mbps up. F293 downstream was
10.68 percent lower and failed the predefined 95 percent acceptance threshold.

## What The Telemetry Proves

Run 2 observed one real recovery context:

- previous fault: `NO_RX_DESC` (`0x20`);
- Linux RX idle: 6150 ms;
- head descriptor: DMA owned (`0x80000000`);
- MAC `FramesRxTotal` advanced at the restart sample;
- MAC progress age: 0 ms;
- DMA missed-frame total: 0;
- counter read failures: 0.

Physical traffic was therefore reaching the Arasan MAC while the Linux RX path
appeared stalled. The recovery responded to real ingress demand, not merely to
an idle interface.

Run 3 retained cumulative last-restart fields from run 2, but its delta contains
no new restart. The reconciled evaluator requires hardware samples only for a
run that actually restarts and treats a zero-millisecond age as a current valid
observation.

## What It Does Not Prove

F293 does not identify whether the final bottleneck is the MAC/DMA handoff,
descriptor servicing, interrupt latency, NAPI scheduling or recovery timing.

It does not prove that earlier recovery is safe or faster. Three runs are also
insufficient to attribute the downstream outlier to the read-only telemetry
patch. The 5 GHz sanity gate was not executed because the performance evaluator
stopped the campaign first.

## Rollback Decision

Rollback was correct because the predefined downstream performance gate failed
and the dual-radio campaign remained incomplete. The exact F292 image was
restored and passed readback, protected-partition and platform gates.

Decision: retain F292. Use F293 as diagnostic evidence for a minimal F299
traffic-demand acceleration experiment while preserving the complete F290
16-poke fallback, cooldown and restart sequence.

## Evidence

- Original immutable campaign result:
  `outputs/campaign/f293-flash-test-20260904T082457Z/result.json`
- Original evaluator result:
  `outputs/campaign/f293-flash-test-20260904T082457Z/physical/f293-evaluation.json`
- Reconciled evaluator result:
  `outputs/campaign/f293-flash-test-20260904T082457Z/physical/f293-evaluation-reconciled.json`
- F293 flash result:
  `%USERPROFILE%/.openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f293-device-bound/flash-one-shot-20260904T082508Z/result.json`
- F292 rollback result:
  `%USERPROFILE%/.openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f292-device-bound/flash-one-shot-20260904T084126Z/result.json`
