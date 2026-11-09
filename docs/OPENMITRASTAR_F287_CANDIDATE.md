# OpenMitraStar F287 Full candidate

Date: 2026-09-03

## Purpose

F287 tests one datapath hypothesis derived from three matched physical F285
2.4 GHz runs: retain the 256-entry RX ring and raise the Topaz EMAC NAPI weight
from 128 to 256 so one poll can drain a complete ring.

## Evidence for the experiment

The F285 three-run median was 14.681 Mbps downstream and 14.265 Mbps upstream.
All six 32 MiB transfers passed with no WLAN errors, drops or allocation
failures, but every run recorded:

- one NO_RX_DESC-attributed RX restart;
- 20-43 NO_RX_DESC interrupts;
- 300-308 sampled NO_RX_DESC states;
- 33-47 exhausted NAPI polls.

The pattern is repeatable and supports a service-quantum experiment. It does
not prove in advance that NAPI-256 will improve throughput.

## Candidate

- Runtime: `lyoko-foundation-6.4.0-f287-emac-napi256-device`
- Candidate bytes: `5259264`
- Candidate SHA-256: `c808359b3ff1a68dd360e1358ae2c258d3a206cb1dd2987c7bbbc401fe149154`
- Full-slot CRC32: `8c931453`
- Full-slot SHA-256: `a3c9fa05b9c23de64466305cd0acc1b5ca3baa005d7667e87b4e67e9e9d6210b`
- Bootbase contract and slot fit: PASS
- Packaged SHA256SUMS: PASS
- Hardware boot: NOT RUN

## Scope

- NAPI weight: 128 to 256.
- RX ring: unchanged at 256 descriptors.
- TX ring: unchanged at 64 descriptors.
- RX buffers and recovery policy: unchanged.
- Rootfs: F286 plus release identity only.
- Realtek/Quantenna modules, firmware, web/API and DTB: unchanged.

The ARC disassembly proves the 256-entry ring allocation and the immediate
value 256 in `qtn_emac_probe`.

## Acceptance

After an explicitly authorized mtd4 promotion, run three matched 32 MiB
bidirectional 2.4 GHz tests. Accept only if:

1. all transfers pass;
2. median downstream and upstream are at least 95 percent of F285;
3. NO_RX_DESC IRQs, sampled states and attributed restarts fall materially;
4. allocation failures, invalid frames and WLAN errors remain zero;
5. SSH and the 5 GHz AP remain stable.
