# OpenMitraStar F172 EMAC NAPI-128 candidate

Date: `2026-09-01`

## Offline decision

F172 is a single-variable direct-EMAC experiment based on the pending F171
rootfs. It does not claim a throughput improvement.

The F167 2.4 GHz 32 MiB run recorded:

- download/upload: approximately `6.88 / 15.13 Mbps`;
- `dma_no_rx_desc_samples +617`;
- `irq_no_rx_desc +15`;
- `napi_budget_exhaustions +133`;
- `rx_restart_reason_no_desc +2`;
- zero RX allocation failures, invalid frames, RX-stopped samples and
  RX-missed samples.

All `133` new budget exhaustions, all `617` sampled `NO_RX_DESC` observations
and both attributed restarts appeared between the first two router samples,
inside the 32 MiB controller-download window. The later upload/soak samples did
not add more of those events.

## Most probable mechanism

The Linux 5.10 direct EMAC has a `128`-descriptor RX ring but registers NAPI
with weight `64`. During a burst, one service pass can leave half the ring
CPU-owned. On the single ARC core the DMA can consume the remaining descriptors
before the next softirq pass, latch `NO_RX_DESC`, stop useful receive progress
and eventually enter the existing full RX restart path.

The OEM Arasan driver uses `board_napi_budget() == 128` and a 1024-descriptor
ring. F172 adopts only the OEM service quantum; it does not enlarge the ring.

`dma_no_rx_desc_samples` is sampled every 10 ms and may count a latched bit
multiple times. The stronger evidence is the simultaneous IRQ count, exhausted
NAPI passes and cause-attributed restarts.

## Single change

```text
qtn-topaz-emac NAPI weight: 64 -> 128
```

The read-only `lyoko_emac_stats` interface reports `napi_weight=128`, allowing
the post-boot gate to prove that the measured kernel is the intended variant.

Unchanged:

- RX ring `128`, RX buffers `2048` bytes;
- per-descriptor RX poll-demand writes;
- restart threshold `16` pokes and cooldown `10000 ms`;
- kernel configuration, DTB and flash layout;
- F171 rootfs health/transaction changes;
- Realtek, Quantenna, TQE, bridge, rates, WPA2 and regulatory configuration;
- protected partitions and `mtd3/linux_safety` rollback.

## Offline build

```powershell
python tools\prepare_f172_emac_napi128_assets.py
python tools\compose_f172_emac_napi128.py
python -m pytest -q tools\test_f172_emac_napi128.py
```

Or run the complete offline pipeline:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\build_f172_emac_napi128.ps1
```

Dry-run the guarded promotion contract without touching hardware:

```powershell
.\tools\build_flash_test_f172_emac_napi128.ps1 -SkipBuild
```

The explicit promotion command is prepared separately and acquires `topaz>`
before starting UART/YMODEM. It is not executed by the offline pipeline.

Evidence analysis:

```powershell
python tools\analyze_f172_emac_starvation.py `
  --output outputs\f3-certification\realtek-2g-f167-32m-20260901\f172-emac-starvation-analysis.json
```

Built artifact:

- File:
  `work/mission-state/q3-persistent-composite-f172-emac-napi128-from-f171/build/openmitrastar-linux510-q3-persistent-f172-emac-napi128-from-f171-LZMA-OFFLINE-NO-FLASH.webformat.bin`
- Bytes: `4,964,352`
- SHA-256: `170a0010273bb9657b5677b4592db2f01660c7654ec85e6abe56fd9e64579984`
- Candidate CRC32: `b87bc61a`
- Full-slot CRC32: `271d8183`
- Kernel LZMA SHA-256: `85ff14ca7b5a0eb33ec6a8812a6f3ed070ca6709e72e2816683f4ec38fa10e90`
- Rootfs SHA-256: `28c3c18abd228935807f22d6bf876d6dbbc888dbfd7561c6d7480d656430d97b`
  — identical to F171.
- Bootbase/slot fit: `PASS`.
- ARC binary contract: `r3=0x80` immediately before `netif_napi_add`, `PASS`.
- Focused regression suite: `26 passed`.

## Exact physical gate for the hardware-owning thread

Do not execute until F171 is either accepted or deliberately superseded and the
main thread explicitly authorizes the exact F172 artifact.

1. Pin exact F172 path, bytes, SHA-256, candidate/full-slot CRC32, Bootbase
   contract, protected-partition baseline and `mtd3` rollback.
2. Prefer one RAM boot if the proven transport/recovery window permits it.
   Otherwise a persistent write may target only `mtd4/linux_live` under the
   normal explicit-authorization contract.
3. After boot require kernel, SquashFS, SSH, F171 dashboard/API health,
   transaction no-op, both radio control planes and bridge membership PASS.
4. Record a quiet 60-second EMAC baseline from `lyoko_emac_stats`.
5. Run three matched 2.4 GHz tests with the same client, channel, distance and
   controller:
   - 32 MiB download first;
   - 32 MiB upload second;
   - router samples every 2-5 seconds.
6. Run one simultaneous 2.4+5 GHz 32 MiB bidirectional test to ensure the larger
   EMAC service quantum does not starve IRQ28/QMAC/SSH.
7. For every run calculate deltas for:
   - throughput and elapsed seconds;
   - `irq_no_rx_desc`, `dma_no_rx_desc_samples`;
   - `napi_polls`, `napi_budget_exhaustions`, `napi_rx_work`;
   - every RX restart reason and throttled restart;
   - IRQ20, IRQ28, IRQ8, netdev errors/drops and SSH continuity.
8. Accept the hypothesis only if all three 2.4 GHz download runs show:
   - zero `rx_restart_reason_no_desc` increments;
   - at least 90% fewer `irq_no_rx_desc` events than the matched F167 rate;
   - no allocation/error/drop regression;
   - median download at least 15% above F167, with upload not more than 5%
     below F167.
   Apply the machine-readable gate with three real summaries:

   ```powershell
   python tools\evaluate_f172_emac_napi128_result.py `
     --candidate-summary <run1>\summary.json `
     --candidate-summary <run2>\summary.json `
     --candidate-summary <run3>\summary.json `
     --output <campaign>\f172-evaluation.json
   ```
9. Reject F172 if restarts persist, latency/SSH/radio scheduling regresses, or
   throughput does not improve. The next experiment must then be separate:
   ring depth or NO_RX_DESC acknowledgement/recovery, never both together.

The complete gated campaign is automated as:

```powershell
.\tools\run_f172_physical_campaign.ps1 `
  -Execute `
  -Ack OPENMITRASTAR_F172_PHYSICAL_CAMPAIGN
```

It refuses to change the Windows Wi-Fi client unless the live kernel exposes
`napi_weight=128` and Lyoko reports `boot-state=ready`. It performs no flash or
router configuration mutation.

## Safety classification

- Offline build only.
- No COM3, router, Windows Wi-Fi, reboot or MTD access performed.
- Physical validation: `NOT_RUN`.
- Improvement claimed: `false`.
