# OpenMitraStar F263 Full current state

## Installed image

- Runtime: `lyoko-foundation-6.0-f263-full-device`
- Target: physical `mtd4/linux_live` only
- Transport: Bootbase TFTP from wired controller `192.168.1.43`
- Candidate bytes: `5246976`
- Candidate SHA-256: `9333feba1fa190e76f60cc1a1cc52a4473aafff3a50d7bbe06b062720ceb869f`
- Full-slot CRC32: `34b37586`
- Full-slot SHA-256: `541d740e411bdf471948a034c977b08267a39df075d2ab27c36ef555045bea6c`
- Prefix compare: PASS
- Protected partitions `mtd0`, `mtd1`, `mtd2`, `mtd3` and `mtd5`: PASS

Primary flash evidence:

`%USERPROFILE%\.openmitrastar\devices\hgw500bna-qcv2-a2-primary\firmware\f263-device-bound\flash-one-shot-20260902T221632Z\result.json`

## Integrated feature set

F263 is the single Full Lyoko line. It combines:

- F223/F247 kernel with NAPI weight 128 and RX ring 256;
- F258/F259 signed package runtime and working IPK decompression;
- F260 BusyBox-compatible transaction and API lock cleanup;
- F261 Quantenna `/bin/ifconfig` backend correction;
- F262 Realtek channel/bandwidth application through verified hostapd restart;
- Foundation 5.4 LED control, config-store API, opkg compatibility and package UI;
- Foundation 6.0 single Developer console and documented ES channel map.

## Proven on hardware

- TFTP transfer: PASS
- mtd4 erase/write/readback: PASS
- Persistent Linux 5.10 boot: PASS
- SSH pinned identity: PASS
- SquashFS root and partition windows: PASS
- `br0`, `wlan0` and `wifi0`: PASS after service convergence
- Web login and protected API: PASS
- Signed package update/search/info/depends/plan/install/remove: PASS
- Package installation remains volatile; `mtd5` hash unchanged: PASS
- Fatal marker gate before the radio-control experiment: PASS

Post-flash evidence:

- `outputs/postflash/f263-device-20260902T221622Z/status.json`
- `outputs/f3-certification/f263-package-20260903-002025/status.json`

## Current physical incident

The dual-radio transaction gate completed the initial health checks and then
lost Ethernet/SSH while invoking the 5 GHz `apply_config` path. The host-side
SSH process was stopped after it exceeded the rollback window. UART did not
respond to SysRq while the device was in that state.

The next hardware action is a physical power cycle. After boot, run read-only
health checks first. Do not immediately repeat the combined dual-radio gate.

The gate runner has been hardened with SSH keepalives and per-band evidence so
future failures terminate and preserve the completed 2.4 GHz result.

## DFS boundary

The Developer UI exposes and documents channels 36-140. Channels 36-48 are the
currently applicable non-DFS set. DFS candidates remain fail-closed because
the Linux 5.10 image still uses `qdrv_radar_compat`, not a proven native radar
detector. The acknowledgement dialog records operator intent but never bypasses
CAC, radar monitoring, channel evacuation, NOP or calibrated power limits.

See `docs/LYOKO_CHANNEL_POLICY_ES.md`.
