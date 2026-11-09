# OpenMitraStar F168-2G TX diagnostic candidate

Date: `2026-09-01`

## Decision

F168-2G is an instrumentation-only candidate derived from installed F167. It
does not claim a throughput fix.

The F167 32 MiB result was approximately `6.875 Mbps` controller download and
`15.129 Mbps` controller upload while the Windows station reported
`130 Mbps MCS15`. The slow direction is:

`controller -> eth0 RX -> br0 -> wlan0 TX -> client`

It is not primarily the `rtl_pci` RX path. That RX path carries the faster
client upload direction. F167 also moved more than 32 MiB through both netdev
paths without new `wlan0` errors or drops.

Two cautions prevent declaring the Realtek TX path healthy:

1. F167 loads `hgw500_force_data_mcs7=1`, but `iw station` reported MCS15. The
   descriptor policy and firmware-reported rate therefore need direct capture.
2. The current rtlwifi completion path fabricates `IEEE80211_TX_STAT_ACK` unless
   the opt-in honest-ACK experiment is enabled. Consequently `tx retries: 0`
   and `tx failed: 0` are not independent RF-success proof.

The same run also recorded two EMAC RX restarts while receiving the download
stream. That is direct evidence of a competing downlink limiter, but F168 does
not change EMAC behavior because this branch is deliberately diagnostic and
Realtek-scoped.

## F168 change

Only `usr/sbin/om-radio-modules` changes. Existing bounded diagnostics are
enabled:

- `rtl_pci hgw500_be_tx_summary=1`
- `rtl8192ee hgw500_tx_close_diag=1`
- `rtl8192ee hgw500_tx_rate_trace=1`

Preserved byte-for-byte from F167:

- kernel and DTB;
- `rtlwifi.ko`, `rtl_pci.ko`, `rtl8192ee.ko` and all dependencies;
- Quantenna modules and configuration;
- EMAC implementation and recovery thresholds;
- bridge topology, rates, crypto, regulatory settings and WPA2 policy;
- SquashFS read-only model and flash layout.

## Built artifact

- Candidate:
  `work/mission-state/q3-persistent-composite-f168-2g-tx-diag-from-f167/build/openmitrastar-linux510-q3-persistent-f168-2g-tx-diag-from-f167-LZMA-OFFLINE-NO-FLASH.webformat.bin`
- Bytes: `4,956,160`
- SHA-256: `6586e513684172e9bbc34aad4775282dfb145f603e394c372eafab5d33ee76cf`
- Candidate CRC32: `71b21c31`
- Full-slot CRC32: `fdab523f`
- Rootfs SHA-256: `a7a49b78fc48a9705e5283965b78ee3ef36c92329974d45e6cdbc26e48187256`
- Bootbase contract: `PASS`
- Slot fit: `PASS`
- Hardware boot/traffic: `NOT_RUN`

Offline verification:

- focused F164-F168 and UART pipeline suite: `19 passed`;
- `SHA256SUMS`: all entries `OK`;
- extracted loader: shell syntax `PASS`;
- extracted Realtek modules match F167:
  - `rtlwifi.ko`: `9b7988816abb5065cd5a2a39defba608d073646aac15c75e244ac5cd95e096ee`
  - `rtl_pci.ko`: `6f85efa424c6aa5b693982ae074d268d2312a3f9262238e8c6f5eda16199df63`
  - `rtl8192ee.ko`: `f014ad53084e1eb3cf7a9083913388ac907f0d254478dd63b0bc9ca054394e85`

`hgw500_oem_tx_report` remains disabled because requesting extra firmware TX
reports is a behavior change. It can become a second experiment only if the
descriptor/ring evidence is insufficient.

## Offline result interpretation

Run:

```powershell
python tools\analyze_f168_2g_tx_evidence.py `
  --summary outputs\f3-certification\realtek-2g-f167-32m-20260901\summary.json `
  --output outputs\f3-certification\realtek-2g-f167-32m-20260901\f168-offline-analysis.json
```

The expected classification is:

`DOWNLINK_LOW_TX_PATH_UNRESOLVED_EMAC_RESTARTS_OBSERVED`

## Exact physical test requested from the hardware-owning thread

Do not run this list until that thread has explicitly authorized the exact
F168 artifact and owns the UART/recovery window.

1. Record F167 control before any change:
   - exact installed full-slot CRC/hash;
   - `sha256sum` of the three Realtek modules;
   - all `/sys/module/rtl_pci/parameters/hgw500_*` and
     `/sys/module/rtl8192ee/parameters/hgw500_*` values;
   - `iw dev wlan0 station dump`, `/proc/net/dev`, IRQ20/IRQ28 and
     `lyoko_emac_stats`.
2. Repeat F167 three times with the same client, channel 1, distance, controller
   endpoint and 32 MiB download/upload order. Capture router samples every
   2-5 seconds. Do not mix 5 GHz traffic into this control.
3. If explicitly authorized, write only the pinned F168 image to
   `mtd4/linux_live`; verify candidate prefix, full-slot hash/CRC and protected
   partition hashes. Preserve manual `mtd3/linux_safety` rollback.
4. After F168 boot, require SSH, hostapd `ENABLED`, WPA2 association, `wlan0` in
   `br0`, unchanged module hashes and the three diagnostic parameters equal
   `Y`. Confirm Quantenna and EMAC configuration are unchanged.
5. Clear the kernel log immediately before each traffic run. Execute three
   identical 32 MiB bidirectional runs, download first and upload second.
6. For every run capture:
   - controller B/s and seconds in both directions;
   - `OMRTLBE`, `OMRTLTXCLOSE`, `OMRTLRA stage=tx-desc`, and existing
     `OMRTL stage=tx-complete` lines;
   - station rate, signal, packets/bytes, retries/failed (not treated as ACK
     proof);
   - `wlan0`, `eth0`, `br0`, IRQ20, IRQ28 and `lyoko_emac_stats` deltas;
   - timestamps of every EMAC restart.
7. Analyze each F168 result with:

   ```powershell
   python tools\analyze_f168_2g_tx_evidence.py `
     --summary <run>\summary.json `
     --trace-log <run>\dmesg.log `
     --output <run>\f168-analysis.json
   ```

8. Decision rules:
   - `AMPDU mostly 0`: investigate BA/aggregation negotiation next; do not tune
     fixed rates first.
   - growing BE queue plus repeated `closed=0` and stagnant HW RP: Realtek TX
     completion/reclaim remains the leading cause.
   - low queue, progressing RP/WP, AMPDU active, but throughput dips align with
     EMAC restarts: return the branch to direct EMAC RX recovery work.
   - no queue/restart correlation: add the separately reviewed OEM TX-report
     experiment; do not infer success from MCS15 or zero retry counters.
9. A performance claim requires the median of three F168 downloads to exceed
   the median of three F167 downloads by at least 15%, with no regression in
   upload, association, management reachability, protected partitions or
   either radio. F168 itself is diagnostic, so no improvement is expected or
   claimed.

## Safety classification

- Offline build: allowed and completed without router access.
- Physical boot/traffic: pending main thread.
- Flash: not executed by this work.
- MTD writes: none.
- UART/COM3: not opened.
- Reboot/power-cycle: not performed.
