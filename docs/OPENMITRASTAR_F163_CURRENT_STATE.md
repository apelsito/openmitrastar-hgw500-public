# OpenMitraStar F163 current state

Snapshot date: `2026-08-31`

## Installed firmware

- Target: `MitraStar HGW-500BNA-QCv2 A2`
- Kernel: `5.10.260-openmitrastar-radiohw`
- Slot: physical `mtd4/linux_live`
- Candidate: `4,376,191` bytes
- SHA-256: `9a3773fa883170f8a9523a4ac79f5f48c0fd6a7501c8475a958190ff53b3f58a`
- Full-slot CRC32: `de140318`
- Full-slot SHA-256: `c5462d457cbbe8a81dd8df7402148ae07e0037e9e2813a23e128c83bf094e259`
- Rollback: preserved `mtd3/linux_safety`, manual UART `ATGO`
- Protected partitions: PASS

Flash evidence:
`work/mission-state/q3-persistent-composite-f163-emac-rxrestart16-from-f162/build/flash-one-shot-20260831T230525Z/result.json`

## Change

F163 starts from stable dual-radio F157, adds the F162 read-only TQE counters,
and changes one fixed-size kernel immediate: the direct EMAC RX DMA restart
threshold is reduced from 63 polls to 16 polls, approximately 15.75 seconds to
4 seconds. Rootfs CPIO, Wi-Fi modules, qdrv/wlan, rates, queues, DMA policy,
rings, bridge topology and security configuration remain unchanged.

## Current evidence

- Persistent boot, Ethernet management and SSH: PASS.
- `br0`: `eth0 + wlan0 + wifi0`.
- 2.4 GHz: WPA2, MCS15/130 Mbps PHY, 8 MiB down and 32 MiB up PASS.
- 2.4 GHz measured throughput: about 5.54 Mbps down and 14.4 Mbps up.
- 5 GHz: WPA2 and bidirectional 8 MiB traffic PASS twice.
- 5 GHz measured throughput: 20.8-28.1 Mbps down and 29.0-35.7 Mbps up.
- No fatal MuC, MMU or kernel marker was observed.
- The Windows 5 GHz oracle recorded one continuity loss in each 120-second
  soak, while router-side association stayed present.

Some nested evidence filenames contain `20260901` because the host clock
crossed midnight; the canonical session date is `2026-08-31`.

## Decision

F163 is the installed diagnostic candidate and a clear 2.4 GHz improvement,
but is not yet the final release candidate. Remaining gates are repeatable 2.4
performance, classification of the 5 GHz client continuity event, DFS and a
long simultaneous dual-radio soak.

Do not enable `fwt_ctrl` speculatively. During the reproduced 2.4 failure the
TQE CPU RX counters remained zero, while the direct EMAC RX DMA stalled and
later recovered. Current evidence therefore points to EMAC recovery/IRQ
handling rather than the Realtek TX ring or TQE NAPI path.
